"""
Dedalus script simulating librational instability in a disk by solving the
incompressible Navier-Stokes equations linearized around a background librating
flow. This script demonstrates solving an initial value problem in the disk.
It can be ran serially or in parallel, and uses the built-in analysis framework
to save data snapshots to HDF5 files. The `plot_snapshots.py` and `plot_scalars.py`
scripts can be used to produce plots from the saved data. The simulation should
take 10 cpu-minutes to run.

The problem is non-dimesionalized using the disk radius and librational frequency,
so the resulting viscosity is related to the Ekman number as:

    nu = Ekman

For incompressible hydro in the disk, we need one tau term for the velocity.
Here we lift to the natural output (k=2) basis.

To run and plot using e.g. 4 processes:
    $ mpiexec -n 4 python3 libration.py
    $ mpiexec -n 4 python3 plot_scalars.py scalars/*.h5
    $ mpiexec -n 4 python3 plot_snapshots.py snapshots/*.h5
"""

import numpy as np
import time
import dedalus.public as d3
from scipy.special import jv
import logging
logger = logging.getLogger(__name__)

# TODO: remove azimuth library? might need to fix DCT truncation
# TODO: automate hermitian conjugacy enforcement
# TODO: finalize filehandlers to process virtual file


# Parameters
Nphi, Nr = 32, 128
Ekman = 1 / 2 / 20**2
Ro = 40
dealias = 3/2
stop_sim_time = 50
timestepper = d3.SBDF2
timestep = 1e-3
dtype = np.float64

# Bases
coords = d3.PolarCoordinates('phi', 'r')
dist = d3.Distributor(coords, dtype=dtype)
basis = d3.DiskBasis(coords, shape=(Nphi, Nr), radius=1, dealias=dealias, dtype=dtype, azimuth_library='matrix')
phi, r = basis.local_grids()
S1_basis = basis.S1_basis(radius=1)

# Fields
u = dist.VectorField(coords, name='u', bases=basis)
p = dist.Field(name='p', bases=basis)
tau = dist.VectorField(coords, name='tau', bases=S1_basis)

# Substitutions
nu = Ekman

lap = lambda A: d3.Laplacian(A, coords)
grad = lambda A: d3.Gradient(A, coords)
integ = lambda A: d3.Integrate(A, coords)
lift_basis = basis.clone_with(k=2) # Natural output basis
lift = lambda A, n: d3.LiftTau(A, lift_basis, n)

# Background librating flow
u0_real = dist.VectorField(coords, bases=basis)
u0_imag = dist.VectorField(coords, bases=basis)
u0_real['g'][0] = Ro * np.real(jv(1, (1-1j)*r/np.sqrt(2*Ekman)) / jv(1, (1-1j)/np.sqrt(2*Ekman)))
u0_imag['g'][0] = Ro * np.imag(jv(1, (1-1j)*r/np.sqrt(2*Ekman)) / jv(1, (1-1j)/np.sqrt(2*Ekman)))
t = dist.Field()
u0 = np.cos(t) * u0_real - np.sin(t) * u0_imag

# Problem
problem = d3.IVP([p, u, tau], time=t, namespace=locals())
problem.add_equation("div(u) = 0")
problem.add_equation("dt(u) - nu*lap(u) + grad(p) + lift(tau,-1) = - dot(u, grad(u0)) - dot(u0, grad(u))")
problem.add_equation("u(r=1) = 0", condition='nphi != 0')
problem.add_equation("azimuthal(u(r=1)) = 0", condition='nphi == 0')
problem.add_equation("p(r=1) = 0", condition='nphi == 0') # Pressure gauge

# Solver
solver = problem.build_solver(timestepper)
solver.stop_sim_time = stop_sim_time

# Initial conditions
u.fill_random('g', seed=42, distribution='standard_normal') # Random noise
u.low_pass_filter(scales=0.25) # Keep only lower fourth of the modes

# Analysis
snapshots = solver.evaluator.add_file_handler('snapshots', sim_dt=0.1, max_writes=20)
snapshots.add_task(u, scales=(4, 1))
scalars = solver.evaluator.add_file_handler('scalars', sim_dt=0.01)
scalars.add_task(integ(0.5*d3.dot(u,u)), name='KE')

# Flow properties
flow = d3.GlobalFlowProperty(solver, cadence=100)
flow.add_property(d3.dot(u,u), name='u2')

# Main loop
hermitian_cadence = 100
try:
    logger.info('Starting loop')
    start_time = time.time()
    while solver.proceed:
        solver.step(timestep)
        if (solver.iteration-1) % 10 == 0:
            max_u = np.sqrt(flow.max('u2'))
            logger.info("Iteration=%i, Time=%e, dt=%e, max(u)=%e" %(solver.iteration, solver.sim_time, timestep, max_u))
        # Impose hermitian symmetry on two consecutive timesteps because we are using a 2-stage timestepper
        if solver.iteration % hermitian_cadence in [0, 1]:
            for f in solver.state:
                f.require_grid_space()
except:
    logger.error('Exception raised, triggering end of main loop.')
    raise
finally:
    end_time = time.time()
    logger.info('Iterations: %i' %solver.iteration)
    logger.info('Sim end time: %f' %solver.sim_time)
    logger.info('Run time: %.2f sec' %(end_time-start_time))
    logger.info('Run time: %f cpu-hr' %((end_time-start_time)/60/60*dist.comm.size))

# Post-processing
if dist.comm.rank == 0:
    scalars.process_virtual_file()

