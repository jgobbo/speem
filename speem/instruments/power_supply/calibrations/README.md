# Calibrations and Calibration Procedure

These are output calibration tables for the SES power supplies 
on the Spin-ToF and the PEEM.

## HV Calibrations
If a voltage V is desired, then we take 
((V - Offset) / Maximum) * 65535 which maps `float -> u16`

This is because the Scienta supplies take a 16 bit 
unsigned number to specify the supply voltage.

## LV Calibrations
