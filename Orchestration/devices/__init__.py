"""Device wrappers used by the MADSci nodes.

formulator_pen_weighing_node drives the XYZ gantry and the tool changer
through their SiLA 2 servers on the cell-side Raspberry Pi 5
(``xyz_gantry_sila``, ``tool_changer_sila``) and the Formulator Pens through
``formulator_pen_ssh``, which runs ``Programming/formulator_pen/run_job.py`` on the
Pen-side Raspberry Pi 5 over SSH. The ``*_fake`` modules stand in for them
without hardware; ``formulator_pen_fake`` simulates a Pico W and the balance.

Nothing is imported here, so each mode imports only the wrappers it uses.
"""
