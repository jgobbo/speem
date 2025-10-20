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


int __stdcall GDS_SUP_Initialize(uint32_t AHandle);
void __stdcall GDS_SUP_Finalize();
bool __stdcall GDS_SUP_Setup();
int __stdcall GDS_SUP_Reset();
int __stdcall GDS_SUP_TestCommunication(int *AID);
char* __stdcall GDS_SUP_GetLibInfo();
int __stdcall GDS_SUP_SetHV(int AAddress, int AValue, int APeriod);
int __stdcall GDS_SUP_SetDAC6(int AAddress, int AValue);
int __stdcall GDS_SUP_SetDAC20(int AAddress, int AValue);
int __stdcall GDS_SUP_Burst();

// uint32_t GDS_SUP_Setup(void );
// uint32_t GDS_SUP_SetHV(uint32_t Address, uint32_t Voltage, uint32_t Period);
// uint32_t GDS_SUP_SetDAC20(int32_t Address, int32_t Voltage);
// uint32_t GDS_SUP_Burst(void );
// uint32_t GDS_SUP_Finalize(void );
