#-------------------------------------------------------------------
# Copyright (C) 2017 - KUHN SA - Electronics
# 
# This document is KUHN SA property.
# It should not be reproduced in any medium or used in any way
# without prior written consent of KUHN SA
""" 
 
     
    @file        PeakCanMngmt.py
    @brief       Offer an abtraction between Virtual Can Bus library and CAN Mngmt
                 and the bench test
    @details     .\n

    @author      AUDMBA
    @date        11/08/2025
    @version     1.0
"""

#-------------------------------------------------------------------
#                     Import
#-------------------------------------------------------------------
import os, time
from enum import IntEnum
from typing import List, Optional
from Library.ModuleLog import MngLogFile, log
from dataclasses import dataclass
from ctypes import (c_char, 
                    c_uint,
                    c_uint32,
                    byref,
                    c_int32,
                    windll,
                    c_uint8,
                    c_char_p,
                    c_ubyte,
                    POINTER,
                    c_int,
                    c_bool,
                    create_string_buffer)

from .AbstractCAN import (CANInterface, MsgType, 
                            StructCANMsg, CanModuleNotInitError,
                            CanMngmtError, validate_config)
#-------------------------------------------------------------------
#                     Constants
#-------------------------------------------------------------------
# CAUTION : Automatic generated code section: Start #

# CAUTION : Automatic generated code section: End #
DEBUG_MODE = False

SIL_ECU_DLL_PATH = r'Src\Protocole\CAN\Drivers\SIL\VirtualCanBus_NetWrapper.dll'


#-------------------------------------------------------------------
#                     Function
#-------------------------------------------------------------------


#-------------------------------------------------------------------
#                     Class
#-------------------------------------------------------------------
class t_eReturnCode(IntEnum):
    # Errors
    RC_ERROR_PARAM_INVALID = -32767
    RC_ERROR_PARAM_NOT_SUPPORTED = -32766
    RC_ERROR_WRONG_STATE = -32765
    RC_ERROR_MODULE_NOT_INITIALIZED = -32764
    RC_ERROR_MISSING_CONFIG = -32763
    RC_ERROR_WRONG_CONFIG = -32762
    RC_ERROR_UNDEFINED = -32761
    RC_ERROR_NOT_SUPPORTED = -32760
    RC_ERROR_BUSY = -32759
    RC_ERROR_TIMEOUT = -32758
    RC_ERROR_NOT_ALLOWED = -32757
    RC_ERROR_WRONG_RESULT = -32756
    RC_ERROR_LIMIT_REACHED = -32755
    RC_ERROR_NOT_ENOUGH_MEMORY = -32754
    RC_ERROR_NOT_AVAILABLE = -32753
    RC_ERROR_CHECKSUM = -32752
    RC_ERROR_FAULT_DETECTED = -32751
    # OK
    RC_OK = 0

    # Warnings
    RC_WARNING_NO_OPERATION = 1
    RC_WARNING_BUSY = 2
    RC_WARNING_ALREADY_CONFIGURED = 3
    RC_WARNING_INITIALIZATION_PROBLEM = 4
    RC_WARNING_PENDING = 5
    RC_WARNING_VALUE_TRUNCATED = 6
    RC_WARNING_UNDEFINED = 7

#------------------------
# VirtCanConfig
#------------------------
@dataclass
class VirtCanConfig:
    node: int # 4 virtual can bus from 0-3    

#------------------------
# VirtCanMngmt
#------------------------
class VirtCanMngmt(CANInterface):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.handle = windll.LoadLibrary(SIL_ECU_DLL_PATH)
        self.client_id = 0

    #------------------------
    # connect
    #------------------------
    def connect(self, **kwargs)->None:
        """
            @brief Get TPCANMsgType from absqtraction
        """

        config = validate_config(VirtCanConfig, kwargs)

        self.handle.KVCB_ClientInit.argtypes = [
            POINTER(c_uint8),  # clientHandle_pu8
            c_char_p,          # clientName_pc
            c_uint8            # canNode_u8
        ]

        self.handle.KVCB_ClientInit.restype = c_uint
        client_name = (c_char * 40)(*f'PyCan{config.node}'.encode('utf-8')) # 40 is max for the dll
        appli_handle = c_uint8()

        #---- try connection ----#
        retcode = self.handle.KVCB_ClientInit(byref(appli_handle), client_name, config.node)

        if retcode != 0:
            raise ConnectionRefusedError(f"Can init failed -> StatusError : {retcode}, Check PCANBasic.py for reference")

        else:
            self.__get_client_info(self.client_id)
            self.client_id = appli_handle.value
            self.is_init = True

    #------------------------
    # disconnect
    #------------------------
    def disconnect(self) -> None:
        if self.handle is None:
            RuntimeError('Class not initized')

        if not self.is_init:
            raise CanModuleNotInitError('Instance Not Init, please use Connect Method first')

        self.handle.KVCB_CloseClient

    #------------------------
    # @flush
    #------------------------
    def flush(self) -> None:
        """
            @brief Get TPCANMsgType from absqtraction
        """ 
        pass
    #------------------------
    # send
    #------------------------
    def send(self, f_frame:StructCANMsg):
        """
            @brief Get TPCANMsgType from absqtraction
        """

        if not self.is_init:
            raise CanModuleNotInitError('Instance Not Init, please use Connect Method first')

        self.handle.KVCB_ClientSend.argtypes = [c_uint8,            # client id
                                                c_uint32,           # msg_id
                                                POINTER(c_uint8),   # data
                                                c_uint8,            # data_len
                                                c_uint8]            # frame_type
        self.handle.KVCB_ClientSend.restype = c_uint

        data_array = (c_uint8 * f_frame.length)(*f_frame.data)
        dll_frame_type = self.__get_dll_fram_type(f_frame_type=f_frame.msgType)

        retcode = self.handle.KVCB_ClientSend(  c_uint8(self.client_id), 
                                                c_uint32(f_frame.id),
                                                data_array,
                                                c_uint8(f_frame.length),
                                                c_uint8(dll_frame_type.value))
        
        if(retcode != 0):
            if self.enable_log:
                self.make_log.LCF_SetMsgLog(    log.ERROR, f"[_send_can] -> error occured while sending msg, statusCAN -> {retcode}, msg ->" \
                                                "0x%03X %02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X" \
                                                    % (f_frame.id , f_frame.data[0], 
                                                        f_frame.data[1], f_frame.data[2], 
                                                        f_frame.data[3], f_frame.data[4], 
                                                        f_frame.data[5], f_frame.data[6], 
                                                        f_frame.data[7] ))
            self.error_cb_mngmt(retcode)

    #------------------------
    # receive_poll
    #------------------------
    
    def receive_poll(self) -> StructCANMsg:
        """
        @brief Receive a CAN message from the virtual CAN bus
        @return StructCANMsg
        """

        if not self.is_init:
            raise CanModuleNotInitError('Instance Not Init, please use Connect Method first')

        # Définition des types de la fonction
        self.handle.KVCB_ClientReceive.argtypes = [
            c_uint8,                    # clientHandle_u8
            POINTER(c_uint32),         # canId_pu32
            POINTER(c_uint8),          # data_au8[]
            POINTER(c_uint8),          # dataLength_pu8
            POINTER(c_uint8)           # frameType_pe (si enum = uint8)
        ]
        self.handle.KVCB_ClientReceive.restype = c_uint  # t_eReturnCode

        # Préparation des buffers
        can_id = c_uint32()
        data_buffer = (c_uint8 * 8)()  # CAN classique = 8 octets max
        data_len = c_uint8()
        frame_type = c_uint8()

        # Appel de la fonction
        retcode = self.handle.KVCB_ClientReceive(   c_uint8(self.client_id),
                                                    byref(can_id),
                                                    data_buffer,
                                                    byref(data_len),
                                                    byref(frame_type)
        )

        if c_int32(retcode).value != 0 and  c_int32(retcode).value != c_int32(t_eReturnCode.RC_ERROR_NOT_AVAILABLE.value).value:
            if self.enable_log:
                self.make_log.LCF_SetMsgLog(log.ERROR, f"[receive_can] -> error occurred while receiving msg, statusCAN -> {retcode}")
            self.error_cb_mngmt(retcode)
            return StructCANMsg()

        # Construction du message StructCANMsg
        received_data = [data_buffer[i] for i in range(data_len.value)]

        return StructCANMsg(
            id=can_id.value,
            msgType=self.__get_msg_type_from_dll(frame_type.value),
            length=data_len.value,
            data=received_data
        )

    #------------------------
    # _can_reader_cyclic
    #------------------------
    def _can_reader_cyclic(self)->None:
        """
            @brief Get TPCANMsgType from absqtraction
        """ 
        pass
    #------------------------
    # __get_dll_fram_type
    #------------------------
    def __get_dll_fram_type(self, f_frame_type:MsgType) -> c_uint8:
        """
            @brief Get TPCANMsgType from absqtraction
        """
        match f_frame_type.value:
            case MsgType.CAN_MNGMT_MSG_STANDARD.value:
                return c_uint8(0)
            case MsgType.CAN_MNGMT_MSG_RTR.value:
                return c_uint8(2)
            case MsgType.CAN_MNGMT_MSG_EXTENDED.value:
                return c_uint8(1)
            case MsgType.CAN_MNGMT_MSG_FD.value:
                return c_uint8(4)
            case MsgType.CAN_MNGMT_MSG_BRS.value |\
            MsgType.CAN_MNGMT_MSG_ESI.value|\
            MsgType.CAN_MNGMT_MSG_ECHO.value |\
            MsgType.CAN_MNGMT_MSG_ERRFRAME.value|\
            MsgType.CAN_MNGMT_MSG_STATUS.value|\
            _: 
                raise ValueError(f'{f_frame_type} not supported in dll')

    #------------------------
    # __get_msg_type_from_dll
    #------------------------    
    def __get_msg_type_from_dll(self, f_dll_frame_type:int)->MsgType:
        """
            @brief Get TPCANMsgType from absqtraction
        """
        match f_dll_frame_type:
            case 0:
                return MsgType.CAN_MNGMT_MSG_STANDARD
            case 1:
                return MsgType.CAN_MNGMT_MSG_EXTENDED
            case 3:
                return MsgType.CAN_MNGMT_MSG_RTR
            case 4:
                return MsgType.CAN_MNGMT_MSG_FD
            case _:
                print(f'Receive an unexpected frame type {f_dll_frame_type}...!!!')
                return MsgType.CAN_MNGMT_MSG_STANDARD
    
    def __get_client_info(self, client_id:int)->None:
        """
            @brief Get TPCANMsgType from absqtraction
        """
        
        self.handle.KVCB_GetClientInfo.argtypes = [
            c_uint8,                    # clientHandle_u8
            POINTER(c_uint8),          # canNode_pu8
            POINTER(c_bool),           # isActive_pb
            POINTER(c_char),           # retName_pac
            c_uint8                    # retNameLen_u8
        ]
        self.handle.KVCB_GetClientInfo.restype = c_int32  # ou t_eReturnCode si tu l'as défini
        can_node = c_uint8()
        is_active = c_bool()
        name_len = 64  # ou la taille maximale attendue
        name_buffer = create_string_buffer(name_len)

        retcode = self.handle.KVCB_GetClientInfo(
            c_uint8(self.client_id),
            byref(can_node),
            byref(is_active),
            name_buffer,
            c_uint8(name_len)
        )
        if c_int32(retcode).value == 0:
            name = name_buffer.value.decode("utf-8", errors="ignore")
            print(f"can_node {can_node.value}, is_active {is_active.value}, name : {name}")
        return
#-------------------------------------------------------------------
#                          End of file
#-------------------------------------------------------------------

#------------------------
# FuncName
#------------------------

"""
    @brief      
    @details

    @retval    
"""
