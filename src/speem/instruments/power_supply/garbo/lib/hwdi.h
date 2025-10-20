/* Notes:
 * I have no idea how this works
 */

uint32_t SC_HWDI_Connect(void);
uint32_t SC_HWDI_CreateBuffer(void);
uint32_t SC_HWDI_CreateDevice(void);
uint32_t SC_HWDI_Disconnect(void);
uint32_t SC_HWDI_DisposeBuffer(void);
uint32_t SC_HWDI_DisposeDevice(void);
uint32_t SC_HWDI_GetBufferData(void);
uint32_t SC_HWDI_GetBufferSize(void);
uint32_t SC_HWDI_GetErrorMessage(void);
uint32_t SC_HWDI_GetLibraryVersion(void);
uint32_t SC_HWDI_GetProperties(void);
uint32_t SC_HWDI_GetPropertyManifest(void);
uint32_t SC_HWDI_Read(void);
uint32_t SC_HWDI_ReadAll(void);
uint32_t SC_HWDI_ReadByte(void);
uint32_t SC_HWDI_ResetTransmission(void);
uint32_t SC_HWDI_SetProperties(void);
uint32_t SC_HWDI_Write(void);