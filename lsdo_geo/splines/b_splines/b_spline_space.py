from dataclasses import dataclass

import m3l
import numpy as np
import array_mapper as am
import scipy.sparse as sps

from lsdo_geo.cython.basis_matrix_surface_py import get_basis_surface_matrix
from lsdo_geo.cython.get_open_uniform_py import get_open_uniform

# from lsdo_geo.splines.b_splines.b_spline import BSpline   # Can't do this. Circular import.


@dataclass
class BSplineSpace(m3l.FunctionSpace):
    name : str
    order : tuple[int]
    parametric_coefficients_shape : tuple[int]
    knots : np.ndarray = None
    knot_indices : list[np.ndarray] = None  # outer list is for parametric dimensions, inner list is for knot indices

    def __post_init__(self):

        self.num_coefficient_elements = np.prod(self.parametric_coefficients_shape)

        self.num_parametric_dimensions = len(self.order)

        if self.knots is None:
            self.knots = np.array([])
            self.knot_indices = []
            for i in range(self.num_parametric_dimensions):
                num_knots = self.order[i] + self.parametric_coefficients_shape[i]
                knots_i = np.zeros((num_knots,))
                get_open_uniform(order=self.order[i], num_coefficients=self.parametric_coefficients_shape[i], knot_vector=knots_i)
                self.knot_indices.append(np.arange(len(self.knots), len(self.knots) + num_knots))
                self.knots = np.hstack((self.knots, knots_i))
        else:
            self.knot_indices = []
            knot_index = 0
            for i in range(self.num_parametric_dimensions):
                num_knots_i = self.order[i] + self.parametric_coefficients_shape[i]
                self.knot_indices.append(np.arange(knot_index, knot_index + num_knots_i))
                knot_index += num_knots_i


    def compute_evaluation_map(self, parametric_coordinates:np.ndarray, parametric_derivative_order:tuple=None,
                               expansion_factor:int=0) -> sps.csc_matrix:
        # NOTE: parametric coordinates are in shape (np,3) where 3 corresponds to u,v,w
        num_parametric_coordinates = parametric_coordinates.shape[-1]
        if parametric_derivative_order is None:
            parametric_derivative_order = (0,)*num_parametric_coordinates
        if type(parametric_derivative_order) is int:
            parametric_derivative_order = (parametric_derivative_order,)*num_parametric_coordinates
        elif len(parametric_derivative_order) == 1 and num_parametric_coordinates != 1:
            parametric_derivative_order = parametric_derivative_order*num_parametric_coordinates

        num_points = np.prod(parametric_coordinates.shape[:-1])
        order_multiplied = 1
        for i in range(len(self.order)):
            order_multiplied *= self.order[i]

        data = np.zeros(num_points * order_multiplied) 
        row_indices = np.zeros(len(data), np.int32)
        col_indices = np.zeros(len(data), np.int32)

        num_coefficient_elements = self.num_coefficient_elements

        if self.num_parametric_dimensions == 2:
            u_vec = parametric_coordinates[:,0].copy()
            v_vec = parametric_coordinates[:,1].copy()
            order_u = self.order[0]
            order_v = self.order[1]
            knots_u = self.knots[self.knot_indices[0]].copy()
            knots_v = self.knots[self.knot_indices[1]].copy()
            get_basis_surface_matrix(order_u, self.parametric_coefficients_shape[0], parametric_derivative_order[0], u_vec, knots_u, 
                order_v, self.parametric_coefficients_shape[1], parametric_derivative_order[1], v_vec, knots_v, 
                len(u_vec), data, row_indices, col_indices)
            
        basis0 = sps.csc_matrix((data, (row_indices, col_indices)), shape=(len(u_vec), self.num_coefficient_elements))

        if expansion_factor > 0:
            expanded_basis = sps.lil_matrix((len(u_vec)*expansion_factor, num_coefficient_elements*expansion_factor))
            for i in range(expansion_factor):
                input_indices = np.arange(i, num_coefficient_elements*expansion_factor, expansion_factor)
                output_indices = np.arange(i, len(u_vec)*expansion_factor, expansion_factor)
                expanded_basis[np.ix_(output_indices, input_indices)] = basis0
            return expanded_basis.tocsc()
        else:
            return basis0
    
    def create_function(self, name:str, coefficients:np.ndarray, num_physical_dimensions:int) -> m3l.Function:
        '''
        Creates a function in this function space.

        Parameters
        ----------
        name : str
            The name of the function.
        coefficients : np.ndarray
            The coefficients of the function.
        num_physical_dimensions : int
            The number of physical dimensions of the function.
        '''
        from lsdo_geo.splines.b_splines.b_spline import BSpline
        return BSpline(name=name, space=self, coefficients=coefficients, num_physical_dimensions=num_physical_dimensions)


if __name__ == "__main__":
    from lsdo_geo.splines.b_splines.b_spline_space import BSplineSpace
    from lsdo_geo.cython.get_open_uniform_py import get_open_uniform

    num_coefficients = 10
    order = 4
    # knots_u = np.zeros((num_coefficients + order))
    # knots_v = np.zeros((num_coefficients + order))
    # get_open_uniform(order=order, num_coefficients=num_coefficients, knot_vector=knots_u)
    # get_open_uniform(order=order, num_coefficients=num_coefficients, knot_vector=knots_v)
    # space_of_cubic_b_spline_surfaces_with_10_cp = BSplineSpace(name='cubic_b_spline_surfaces_10_cp', order=(order,order), knots=(knots_u,knots_v))
    space_of_cubic_b_spline_surfaces_with_10_cp = BSplineSpace(name='cubic_b_spline_surfaces_10_cp', order=(order,order),
                                                              parametric_coefficients_shape=(num_coefficients,num_coefficients))

    parametric_coordinates = np.array([
        [0., 0.],
        [0., 1.],
        [1., 0.],
        [1., 1.],
        [0.5, 0.5],
        [0.25, 0.75]
    ])
    eval_map = \
        space_of_cubic_b_spline_surfaces_with_10_cp.compute_evaluation_map(parametric_coordinates=parametric_coordinates, expansion_factor=3)
    derivative_map = \
        space_of_cubic_b_spline_surfaces_with_10_cp.compute_evaluation_map(
            parametric_coordinates=parametric_coordinates, parametric_derivative_order=(1,1))
    second_derivative_map = \
        space_of_cubic_b_spline_surfaces_with_10_cp.compute_evaluation_map(
            parametric_coordinates=parametric_coordinates, parametric_derivative_order=(2,2))