#-------------------------------------------------------------------
# Copyright (C) 2017 - KUHN SA - Electronics
# 
# This document is KUHN SA property.
# It should not be reproduced in any medium or used in any way
# without prior written consent of KUHN SA
#-------------------------------------------------------------------
""" 
 
     
    @file        PeakCanMngmt.py
    @brief       Offer an abtraction between PCAN library and CAN Mngmt
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
import importlib
from typing import List, Optional
from Library.ModuleLog import MngLogFile, log
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from threading import Thread,Event
from queue import Queue, Empty
from ..Drivers.Peak.Src.PCANBasic import *
from .AbstractCAN import (CANInterface, MsgType, 
                            StructCANMsg, CanModuleNotInitError,
                            CanMngmtError, validate_config)
#-------------------------------------------------------------------
#                     Constants
#-------------------------------------------------------------------
# CAUTION : Automatic generated code section: Start #

# CAUTION : Automatic generated code section: End #
DEBUG_MODE = False



#-------------------------------------------------------------------
#                     Function
#-------------------------------------------------------------------


#-------------------------------------------------------------------
#                     Class
#-------------------------------------------------------------------
#------------------------
# PeakCanConfig
#------------------------
@dataclass
class PeakCanConfig:
    pcan_usb: str # from TPCANHandle
    pcan_baudrate: str # from TPCANBaudrate

#------------------------
# PeakCanMngmt
#------------------------
class PeakCanMngmt(CANInterface):
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.handle = PCANBasic()
        self.usb_bus: TPCANHandle

    #------------------------
    # @connect
    #------------------------
    def connect(self, **kwargs)-> None:
        """
            @brief Get TPCANMsgType from absqtraction
        """ 
        if self.handle is None:
            RuntimeError('Class not initized')

        config = validate_config(PeakCanConfig, kwargs)

        pcan_module = importlib.import_module("Protocole.CAN.Drivers.Peak.Src.PCANBasic")
        self.usb_bus = getattr(pcan_module, config.pcan_usb)
        
        status_can_bus = self.handle.Initialize(self.usb_bus, getattr(pcan_module,config.pcan_baudrate))

        if(status_can_bus != PCAN_ERROR_OK):
            raise ConnectionRefusedError(f"Can init failed -> StatusError : {self.handle.GetErrorText(status_can_bus)}, Check PCANBasic.py for reference")
        else:
            self.is_init = True

    #------------------------
    # @disconnect
    #------------------------
    def disconnect(self) -> None:
        if self.handle is None:
            RuntimeError('Class not initized')

        if not self.is_init:
            raise CanModuleNotInitError('Instance Not Init, please use Connect Method first')
        
        self.handle.Uninitialize(self.usb_bus)
    #------------------------
    # @send
    #------------------------
    def send(self, f_frame:StructCANMsg):
        """
            @brief Get TPCANMsgType from absqtraction
        """ 
        if not self.is_init:
            raise CanModuleNotInitError('Instance Not Init, please use Connect Method first')
            
        peak_can_struct = TPCANMsg()
        peak_can_struct.ID = f_frame.id
        peak_can_struct.LEN = f_frame.length
        peak_can_struct.MSGTYPE = self._get_peak_msg_type(f_frame.msgType)
        peak_can_struct.DATA = [f_frame.data[idx_data] for idx_data in range(0, f_frame.length)]

        status = self.handle.Write(self.usb_bus, peak_can_struct)

        if(status != PCAN_ERROR_OK):
            if self.enable_log:
                self.make_log.LCF_SetMsgLog(log.ERROR, f"[_send_can] -> error occured while sending msg, statusCAN -> {self.handle.GetErrorText(status_can_bus)}, msg ->" \
                                        "0x%03X %02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X" \
                                            % (f_frame.id , f_frame.data[0], 
                                                f_frame.data[1], f_frame.data[2], 
                                                f_frame.data[3], f_frame.data[4], 
                                                f_frame.data[5], f_frame.data[6], 
                                                f_frame.data[7] ))
            self.error_cb_mngmt(status)

    #------------------------
    # @receive_poll
    #------------------------
    def receive_poll(self) ->StructCANMsg:
        """
            @brief Get TPCANMsgType from absqtraction
        """ 
        can_status:TPCANStatus
        can_struct:StructCANMsg = StructCANMsg()
        peak_can_struct:TPCANMsg
        checksum_ui = 0

        if not self.is_init:
            raise CanModuleNotInitError('Instance Not Init, please use Connect Method first')

        can_status, peak_can_struct, timestamp = self.handle.Read(self.usb_bus)

        if can_status == PCAN_ERROR_OK:
            for index in range(0,self._MC_DLC_8):
                checksum_ui += peak_can_struct.DATA[index]

            if(checksum_ui != 0 and checksum_ui != 8):
                # Manage CAN logging
                if(self.enable_log == True):
                    self.make_log.LCF_SetMsgLog(log.INFO,"Rcv  : 0x%03X %02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X" \
                                                    % (peak_can_struct.ID     , peak_can_struct.DATA[0],             
                                                        peak_can_struct.DATA[1], peak_can_struct.DATA[2], 
                                                        peak_can_struct.DATA[3], peak_can_struct.DATA[4], 
                                                        peak_can_struct.DATA[5], peak_can_struct.DATA[6], 
                                                        peak_can_struct.DATA[7] ))
            #---- copy data ----#
            can_struct = StructCANMsg(peak_can_struct.ID, MsgType.CAN_MNGMT_MSG_STANDARD, peak_can_struct.LEN, peak_can_struct.DATA, int(timestamp.millis))
        
        elif can_status == PCAN_ERROR_QRCVEMPTY:
            pass # OK 

        else:
                print(f"[ERROR] : an error occured in thread reading -> pcan status {self.handle.GetErrorText(can_status)}")
        return can_struct
    




    #------------------------
    # @flush
    #------------------------
    def flush(self) -> None:
        """
            @brief Get TPCANMsgType from absqtraction
        """ 
        if not self.is_init:
            raise CanModuleNotInitError('Instance Not Init, please use Connect Method first')

        self.handle.Reset(self.usb_bus)
    
    #------------------------
    # _can_reader_cyclic
    #------------------------
    def _can_reader_cyclic(self)->None:
        """
            @brief Get TPCANMsgType from absqtraction
        """ 
        last_time_rec = time.time()
        cnt_buff_log:int = 0
        buffer_log:str = ''

        while not self._stop_rx_thread.is_set():
            current_time = time.time()
            result, msg, timestamp = self.handle.Read(self.usb_bus)

            if result == PCAN_ERROR_OK:
                last_time_rec = current_time
                self._receive_queue.put((msg, timestamp))

                if self.enable_log:
                    cnt_buff_log += 1
                    buffer_log += "[%02X] : 0x%03X %02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X\n" \
                                                    % (timestamp.millis, msg.ID     , msg.DATA[0],             
                                                        msg.DATA[1], msg.DATA[2], 
                                                        msg.DATA[3], msg.DATA[4], 
                                                        msg.DATA[5], msg.DATA[6], 
                                                        msg.DATA[7])
                    if cnt_buff_log > 3000:
                        self.make_log.LCF_SetMsgLog(log.INFO, buffer_log)
                        buffer_log = ''
                        cnt_buff_log = 0

            elif result == PCAN_ERROR_QRCVEMPTY:
                if (current_time - last_time_rec) > 5: # seconds 
                    print('[WARNING] No data received in 5 seconds')
                    last_time_rec = current_time
                time.sleep(0.001) 

            else:                
                print(f'[WARNING] : an error occured on Peak Device -> {self.handle.GetErrorText(result)}')
                self._try_reconexion()
            

    #-------------------------
    # _get_peak_msg_type
    #-------------------------
    def _get_peak_msg_type(self, f_msg_type:MsgType)->TPCANMessageType:
        """
            @brief Get TPCANMsgType from absqtraction
        """ 
        match f_msg_type.value:
            case MsgType.CAN_MNGMT_MSG_STANDARD.value:
                return PCAN_MESSAGE_STANDARD
            case MsgType.CAN_MNGMT_MSG_RTR.value:
                return PCAN_MESSAGE_RTR
            case MsgType.CAN_MNGMT_MSG_EXTENDED.value:
                return PCAN_MESSAGE_EXTENDED
            case MsgType.CAN_MNGMT_MSG_FD.value:
                return PCAN_MESSAGE_FD
            case MsgType.CAN_MNGMT_MSG_BRS.value:
                return PCAN_MESSAGE_BRS
            case MsgType.CAN_MNGMT_MSG_ESI.value:
                return PCAN_MESSAGE_ESI
            case MsgType.CAN_MNGMT_MSG_ECHO.value:
                return PCAN_MESSAGE_ECHO
            case MsgType.CAN_MNGMT_MSG_ERRFRAME.value:
                return PCAN_MESSAGE_ERRFRAME
            case MsgType.CAN_MNGMT_MSG_STATUS.value:
                return PCAN_MESSAGE_STATUS
            case _: 
                #---- should not arrive here ----#
                return TPCANMessageType(PCAN_MESSAGE_STANDARD)

    #-------------------------
    # _get_peak_msg_type
    #-------------------------
    def get_msg_type_from_peak(self, peak_msg_type: TPCANMessageType) -> MsgType:
        """
        @brief Get MsgType abstraction from TPCANMessageType
        """
        if peak_msg_type == PCAN_MESSAGE_STANDARD:
            return MsgType.CAN_MNGMT_MSG_STANDARD
        elif peak_msg_type == PCAN_MESSAGE_RTR:
            return MsgType.CAN_MNGMT_MSG_RTR
        elif peak_msg_type == PCAN_MESSAGE_EXTENDED:
            return MsgType.CAN_MNGMT_MSG_EXTENDED
        elif peak_msg_type == PCAN_MESSAGE_FD:
            return MsgType.CAN_MNGMT_MSG_FD
        elif peak_msg_type == PCAN_MESSAGE_BRS:
            return MsgType.CAN_MNGMT_MSG_BRS
        elif peak_msg_type == PCAN_MESSAGE_ESI:
            return MsgType.CAN_MNGMT_MSG_ESI
        elif peak_msg_type == PCAN_MESSAGE_ECHO:
            return MsgType.CAN_MNGMT_MSG_ECHO
        elif peak_msg_type == PCAN_MESSAGE_ERRFRAME:
            return MsgType.CAN_MNGMT_MSG_ERRFRAME
        elif peak_msg_type == PCAN_MESSAGE_STATUS:
            return MsgType.CAN_MNGMT_MSG_STATUS
        else:
            return MsgType.CAN_MNGMT_MSG_STANDARD
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
