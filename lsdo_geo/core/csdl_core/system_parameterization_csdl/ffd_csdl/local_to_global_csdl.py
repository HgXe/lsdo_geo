import csdl
from csdl_om import Simulator
import numpy as np

class LocalToGlobalCSDL(csdl.Model):
    '''
    Rotates FFD Blocks from local coordinate frame to geometry coordinate frame.
    '''

    def initialize(self):
        self.parameters.declare('ffd_set')

    def define(self):
        ffd_set = self.parameters['ffd_set']

        rotated_ffd_coefficients = self.declare_variable('rotated_ffd_coefficients', val=ffd_set.rotated_coefficients_local_frame)

        # Not vectorized for now for simplicity and to avoid storage of very large tensors
        NUM_PARAMETRIC_DIMENSIONS = 3
        if ffd_set.num_dof != 0:
            coefficients = self.create_output('ffd_coefficients', shape=(ffd_set.num_coefficients,NUM_PARAMETRIC_DIMENSIONS))
        else:   # Purely so CSDL doesn't throw an error for the model not doing anything
            self.create_input('dummy_input_local_to_global', val=0.)
        starting_index = 0
        for ffd_block in list(ffd_set.active_ffd_blocks.values()):
            ending_index = starting_index + ffd_block.num_coefficients

            ffd_block_rotated_coefficients = rotated_ffd_coefficients[starting_index:ending_index,:]

            # make mapping a csdl variable in order to use it for matmat
            global_to_local_rotation = self.create_input(f'{ffd_block.name}_local_to_global_rotation', ffd_block.local_to_global_rotation.T)
            # Apply rotation to global frame
            coefficients_rotated_global_frame = csdl.matmat(ffd_block_rotated_coefficients, global_to_local_rotation)
            # coefficients_rotated_back = csdl.reorder_axes(coefficients_rotated_back_wrong_axis, 'ij->ji')
            coefficients_rotated_back_reshaped = csdl.reshape(coefficients_rotated_global_frame, ffd_block.primitive.shape)

            # Apply translation to global frame
            coefficients_reshaped = coefficients_rotated_back_reshaped + ffd_block.local_to_global_translations
            ffd_block_coefficients = csdl.reshape(coefficients_reshaped, (ffd_block.num_coefficients, NUM_PARAMETRIC_DIMENSIONS))

            coefficients[starting_index:ending_index,:] = ffd_block_coefficients
            starting_index = ending_index


if __name__ == "__main__":
    import csdl
    # from csdl_om import Simulator
    from python_csdl_backend import Simulator
    import numpy as np
    from vedo import Points, Plotter

    from lsdo_geo.caddee_core.system_representation.system_representation import SystemRepresentation
    system_representation = SystemRepresentation()
    spatial_rep = system_representation.spatial_representation
    # from lsdo_geo.caddee_core.system_parameterization.system_parameterization import SystemParameterization
    # system_parameterization = SystemParameterization()

    '''
    Single FFD Block
    '''
    system_representation = SystemRepresentation()
    spatial_rep = system_representation.spatial_representation
    file_path = 'models/stp/'
    spatial_rep.import_file(file_name=file_path+'rect_wing.stp')

    # Create Components
    from lsdo_geo.caddee_core.system_representation.component.component import LiftingSurface, Component
    wing_primitive_names = list(spatial_rep.get_primitives(search_names=['Wing']).keys())
    wing = LiftingSurface(name='wing', spatial_representation=spatial_rep, primitive_names=wing_primitive_names)  # TODO add material arguments
    system_representation.add_component(wing)

    # # Parameterization
    from lsdo_geo.caddee_core.system_parameterization.free_form_deformation.ffd_functions import create_cartesian_enclosure_volume
    from lsdo_geo.caddee_core.system_parameterization.free_form_deformation.ffd_block import SRBGFFDBlock

    wing_geometry_primitives = wing.get_geometry_primitives()
    wing_ffd_b_spline_volume = create_cartesian_enclosure_volume(wing_geometry_primitives, num_coefficients=(11, 2, 2), order=(4,2,2), xyz_to_uvw_indices=(1,0,2))
    wing_ffd_block = SRBGFFDBlock(name='wing_ffd_block', primitive=wing_ffd_b_spline_volume, embedded_entities=wing_geometry_primitives)

    wing_ffd_block.add_rotation_u(name='twist_distribution', order=4, num_dof=10, value=-1/2*np.array([0., 0.11, 0.22, 0.33, 0.44, 0.44, 0.33, 0.22, 0.11, 0.]))
    wing_ffd_block.add_rotation_v(name='wingtip_twist', order=4, num_dof=10, value=-np.array([np.pi/2, 0., 0., 0., 0., 0., 0., 0., 0., -np.pi/2]))
    wing_ffd_block.add_translation_w(name='wingtip_translation', order=4, num_dof=10, value=np.array([2., 0., 0., 0., 0., 0., 0., 0., 0., 2.]))

    from lsdo_geo.caddee_core.system_parameterization.free_form_deformation.ffd_set import SRBGFFDSet
    ffd_set = SRBGFFDSet(name='ffd_set', ffd_blocks={wing_ffd_block.name : wing_ffd_block})

    ffd_set.setup(project_embedded_entities=False)
    affine_section_properties = ffd_set.evaluate_affine_section_properties()
    affine_deformed_ffd_coefficients = ffd_set.evaluate_affine_block_deformations()
    rotational_section_properties = ffd_set.evaluate_rotational_section_properties()
    rotated_ffd_coefficients = ffd_set.evaluate_rotational_block_deformations()
    ffd_coefficients = ffd_set.evaluate_coefficients()
    # print('Python evaluation: FFD coefficients: \n', rotated_ffd_coefficients)

    sim = Simulator(LocalToGlobalCSDL(ffd_set=ffd_set))
    sim.run()
    # sim.visualize_implementation()        # Only csdl_om can do this

    # print('CSDL evaluation: FFD coefficients: \n', sim['ffd_coefficients'])
    print("Python and CSDL difference", np.linalg.norm(sim['ffd_coefficients'] - ffd_coefficients))

    wing_ffd_block.plot_sections(coefficients=sim['ffd_coefficients'].reshape(wing_ffd_b_spline_volume.shape), plot_embedded_entities=False, opacity=0.75, show=True)
    wing_ffd_block.plot_sections(coefficients=ffd_coefficients.reshape(wing_ffd_b_spline_volume.shape), plot_embedded_entities=False, opacity=0.75, show=True)
    # wing_ffd_b_spline_volume.coefficients = sim['rotated_ffd_coefficients'].reshape(wing_ffd_b_spline_volume.shape)
    # wing_ffd_b_spline_volume.plot()
    

    '''
    Multiple FFD blocks
    '''
    file_path = 'models/stp/'
    spatial_rep.import_file(file_name=file_path+'lift_plus_cruise_final_3.stp')

    # Create Components
    from lsdo_geo.caddee_core.system_representation.component.component import LiftingSurface
    wing_primitive_names = list(spatial_rep.get_primitives(search_names=['Wing']).keys())
    wing = LiftingSurface(name='wing', spatial_representation=spatial_rep, primitive_names=wing_primitive_names)  # TODO add material arguments
    tail_primitive_names = list(spatial_rep.get_primitives(search_names=['Tail_1']).keys())
    horizontal_stabilizer = LiftingSurface(name='tail', spatial_representation=spatial_rep, primitive_names=tail_primitive_names)  # TODO add material arguments
    system_representation.add_component(wing)
    system_representation.add_component(horizontal_stabilizer)

    # # Parameterization
    from lsdo_geo.caddee_core.system_parameterization.free_form_deformation.ffd_functions import create_cartesian_enclosure_volume
    from lsdo_geo.caddee_core.system_parameterization.free_form_deformation.ffd_block import SRBGFFDBlock

    wing_geometry_primitives = wing.get_geometry_primitives()
    wing_ffd_b_spline_volume = create_cartesian_enclosure_volume(wing_geometry_primitives, num_coefficients=(11, 2, 2), order=(4,2,2), xyz_to_uvw_indices=(1,0,2))
    wing_ffd_block = SRBGFFDBlock(name='wing_ffd_block', primitive=wing_ffd_b_spline_volume, embedded_entities=wing_geometry_primitives)
    wing_ffd_block.add_rotation_u(name='twist_distribution', order=4, num_dof=10, value=-1/2*np.array([0., 0.11, 0.22, 0.33, 0.44, 0.44, 0.33, 0.22, 0.11, 0.]))

    horizontal_stabilizer_geometry_primitives = horizontal_stabilizer.get_geometry_primitives()
    horizontal_stabilizer_ffd_b_spline_volume = create_cartesian_enclosure_volume(horizontal_stabilizer_geometry_primitives, num_coefficients=(11, 2, 2), order=(4,2,2), xyz_to_uvw_indices=(1,0,2))
    horizontal_stabilizer_ffd_block = SRBGFFDBlock(name='horizontal_stabilizer_ffd_block', primitive=horizontal_stabilizer_ffd_b_spline_volume, embedded_entities=horizontal_stabilizer_geometry_primitives)
    horizontal_stabilizer_ffd_block.add_rotation_u(name='horizontal_stabilizer_twist_distribution', order=1, num_dof=1, value=np.array([np.pi/10]))

    # plotting_elements = wing_ffd_block.plot(plot_embedded_entities=False, show=False)
    # plotting_elements = horizontal_stabilizer_ffd_block.plot(plot_embedded_entities=False, show=False, additional_plotting_elements=plotting_elements)
    # spatial_rep.plot(additional_plotting_elements=plotting_elements)

    from lsdo_geo.caddee_core.system_parameterization.free_form_deformation.ffd_set import SRBGFFDSet
    ffd_set = SRBGFFDSet(name='ffd_set', ffd_blocks={wing_ffd_block.name : wing_ffd_block, horizontal_stabilizer_ffd_block.name : horizontal_stabilizer_ffd_block})

    ffd_set.setup(project_embedded_entities=False)
    affine_section_properties = ffd_set.evaluate_affine_section_properties()
    rotational_section_properties = ffd_set.evaluate_rotational_section_properties()
    affine_deformed_ffd_coefficients = ffd_set.evaluate_affine_block_deformations()
    rotated_ffd_coefficients = ffd_set.evaluate_rotational_block_deformations()
    ffd_coefficients = ffd_set.evaluate_coefficients()
    # print('Python evaluation: FFD control points: \n', rotated_ffd_coefficients)

    sim = Simulator(LocalToGlobalCSDL(ffd_set=ffd_set))
    sim.run()
    # sim.visualize_implementation()    $ Only usable with csdl_om

    # print('CSDL evaluation: FFD coefficients: \n', sim['ffd_coefficients'])
    print("Python and CSDL difference", np.linalg.norm(sim['ffd_coefficients'] - ffd_coefficients))

    wing_ffd_block.plot_sections(coefficients=(sim['ffd_coefficients'][0:11*2*2,:]).reshape(wing_ffd_b_spline_volume.shape), plot_embedded_entities=False, opacity=0.75, show=True)
    horizontal_stabilizer_ffd_block.plot_sections(coefficients=(sim['ffd_coefficients'][11*2*2:,:]).reshape(horizontal_stabilizer_ffd_b_spline_volume.shape), plot_embedded_entities=False, opacity=0.75, show=True)


    # wing_ffd_b_spline_volume.coefficients = (sim['rotated_ffd_coefficients'][0:11*2*2,:]).reshape(wing_ffd_b_spline_volume.shape)
    # wing_ffd_b_spline_volume.plot()
    # horizontal_stabilizer_ffd_b_spline_volume.coefficients = (sim['rotated_ffd_coefficients'][11*2*2:,:]).reshape(horizontal_stabilizer_ffd_b_spline_volume.shape)
    # horizontal_stabilizer_ffd_b_spline_volume.plot()