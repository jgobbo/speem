/* Notes:
 * Uses stdcall conventions.
 * The ordering for calls is:
 *
 * GDS_SUP_Initialize(0);
 * GDS_SUP_Setup(0)
 * GDS_SUP_SetHV(...);
 * GDS_SUP_SetDAC20(...);
 * GDS_SUP_Burst();
 *
 */


uint32_t GDS_SUP_Setup(void );
uint32_t GDS_SUP_Initialize(uint32_t handle);

uint32_t GDS_SUP_SetHV(uint32_t Address, uint32_t Voltage, uint32_t Period);
uint32_t GDS_SUP_SetDAC20(int32_t Address, int32_t Voltage);
uint32_t GDS_SUP_Burst(void );

uint32_t GDS_SUP_Finalize(void );
