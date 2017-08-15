"""
Domain class definition.
"""

import logging
import numpy as np

from ..tools.cache import CachedMethod, CachedClass, CachedAttribute
from ..tools.general import unify_attributes

logger = logging.getLogger(__name__.split('.')[-1])


def expand_spaces(spaces):
    """Expand list of spaces to tuple including constant spaces."""
    # Verify same distributor
    dist = unify_attributes(spaces, 'dist')
    # Verify spaces are non-overlapping
    if len(spaces) > 1:
        axes_sets = [set(space.axes) for space in spaces]
        if set.intersection(*axes_sets):
            raise ValueError("Overlapping spaces specified.")
    # Build full space tuple
    full_spaces = dist.constant_spaces.copy()
    for space in spaces:
        for axis in space.axes:
            full_spaces[axis] = space
    return tuple(full_spaces)


class Domain(metaclass=CachedClass):
    """Object representing the direct product of a set of spaces."""

    @classmethod
    def _preprocess_args(cls, *args, **kw):
        # Expand spaces for proper caching
        args = list(args)
        args[0] = expand_spaces(args[0])
        return tuple(args), kw

    def __init__(self, spaces):
        # Spaces checked and expanded during preprocessing
        self.dist = spaces[0].dist
        self.spaces = spaces

    @classmethod
    def from_dist(cls, dist):
        return cls(dist.constant_spaces)

    @classmethod
    def from_bases(cls, bases):
        return cls([basis.space for basis in bases])

    @CachedAttribute
    def dealias(self):
        return tuple(space.dealias for space in self.spaces)

    @CachedAttribute
    def constant(self):
        return tuple(space.constant for space in self.spaces)

    @CachedAttribute
    def group_shape(self):
        """Compute group shape."""
        shape = np.zeros(self.dist.dim, dtype=int)
        for axis, space in enumerate(self.spaces):
            subaxis = axis - space.axes[0]
            shape[axis] = space.group_shape[subaxis]
        return tuple(shape)

    @CachedAttribute
    def global_coeff_shape(self):
        """Compute global coefficient shape."""
        shape = np.zeros(self.dist.dim, dtype=int)
        for axis, space in enumerate(self.spaces):
            subaxis = axis - space.axes[0]
            shape[axis] = space.shape[subaxis]
        return tuple(shape)

    def global_grid_shape(self, scales):
        """Compute global grid shape."""
        # Remedy scales before calling cached method
        scales = self.dist.remedy_scales(scales)
        return self._global_grid_shape(scales)

    @CachedMethod
    def _global_grid_shape(self, scales):
        shape = np.zeros(self.dist.dim, dtype=int)
        for axis, space in enumerate(self.spaces):
            subaxis = axis - space.axes[0]
            shape[axis] = space.grid_shape(scales[axis])[subaxis]
        return tuple(shape)

    # def expand_bases(self, bases):
    #     exp_bases = [None] * self.domain.dim
    #     for basis in bases:
    #         if basis is not None:
    #             if exp_bases[basis.space.axis] is not None:
    #                 raise ValueError("Degenerate bases.")
    #             exp_bases[basis.space.axis] = basis
    #     return tuple(exp_bases)

    # def __contains__(self, item):
    #     if isinstance(item, Subdomain):
    #         for axis in range(self.domain.dim):
    #             if item.spaces[axis] not in {None, self.spaces[axis]}:
    #                 return False
    #         return True
    #     else:
    #         space = self.domain.get_space_object(item)
    #         return (space in self.spaces)

    # @CachedMethod
    # def grid_spacing(self, axis, scales=None):
    #     """Compute grid spacings along one axis."""
    #     scales = self.remedy_scales(scales)
    #     # Compute spacing on global basis grid
    #     # This includes inter-process spacings
    #     grid = self.bases[axis].grid(scales[axis])
    #     spacing = np.gradient(grid)
    #     # Restrict to local part of global spacing
    #     slices = self.dist.grid_layout.slices(scales)
    #     spacing = spacing[slices[axis]]
    #     # Reshape as multidimensional vector
    #     spacing = reshape_vector(spacing, self.dim, axis)
    #     return spacing

