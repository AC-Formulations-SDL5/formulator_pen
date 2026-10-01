# formulator_pen_weighing_node image: MADSci base + the device libraries.
# The base image's runtime venv is /home/madsci/MADSci/.venv; install there.
# sila2: gantry and tool changer; paramiko: SSH to the Pen-side Pi;
# pyserial/pandas/openpyxl: formulator_pen, imported by the fake Pen.
FROM ghcr.io/ad-sdl/madsci:v0.8.0
RUN uv pip install --python /home/madsci/MADSci/.venv/bin/python \
    sila2 paramiko pyserial pandas openpyxl
