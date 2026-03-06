#-------------------------------------------------------------------
# Copyright (C) 2017 - KUHN SA - Electronics
# 
# This document is KUHN SA property.
# It should not be reproduced in any medium or used in any way
# without prior written consent of KUHN SA
#-------------------------------------------------------------------
""" 
 
     
    @file        AbstractCAN.py
    @brief       Determine the method commoin with all libraries
                Peak, Dll, Vector etc. The software will not be base on 
                as certain library and every python class to Interface 
                a lib will have the same method
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
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from threading import Thread,Event
from queue import Queue, Empty, Full

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
def validate_config(config_class, kwargs):
    try:
        return config_class(**kwargs)
    except TypeError as e:
        raise ValueError(f"Arguments invalides pour {config_class.__name__}: {e}")



#-------------------------------------------------------------------
#                     Class
#-------------------------------------------------------------------
class MsgType(IntEnum):
    CAN_MNGMT_MSG_STANDARD = 0
    CAN_MNGMT_MSG_RTR = 1
    CAN_MNGMT_MSG_EXTENDED = 2
    CAN_MNGMT_MSG_FD = 2
    CAN_MNGMT_MSG_BRS = 3
    CAN_MNGMT_MSG_ESI = 4
    CAN_MNGMT_MSG_ECHO = 5
    CAN_MNGMT_MSG_ERRFRAME = 6
    CAN_MNGMT_MSG_STATUS = 7
#------------------------
# CanMngmtError
#------------------------
class CanMngmtError(IntEnum):
    ErrorTimeout = 0 # no msg received after x ms
    ErrorLost = 1 # gate close unexpectedly

@dataclass
class StructCANMsg:
    id: int = 0
    msgType: MsgType = MsgType.CAN_MNGMT_MSG_EXTENDED
    length: int = 0
    data: List[int] = field(default_factory=list)
    timestamp:int = 0

#------------------------
# CanMngmtOptionError
#------------------------
class CanMngmtOptionError(Exception):
    def __init__(self, f_msg_str) -> None:
        super().__init__(f_msg_str)

#------------------------
# CanModuleNotInitError
#------------------------
class CanModuleNotInitError(Exception):
    def __init__(self, f_msg_str) -> None:
        super().__init__(f_msg_str)

#------------------------
# CANInterface
#------------------------
class CANInterface(ABC):
    
    _MC_DLC_8 = 8

    def __init__(self, **kwargs) -> None:
        super().__init__()
        self.enable_log = kwargs.get('canlogging', False)
        self.error_cb_mngmt = kwargs.get('error_cb', self.default_error_handler)
        self.is_init = False
        # Bounded RX queue to avoid unbounded memory growth if UI/consumer lags.
        self._receive_queue: Queue = Queue(maxsize=8192)
        self._rx_thread: Optional[Thread] = None
        self._stop_rx_thread = Event()
        self._stats = {
            "low_rx_total": 0,      # frame recu du driver/socket
            "low_queue_total": 0,   # frame place dans la queue interne CAN
        }
        dir_log_path = kwargs.get('dir_log_path', '')
        if self.enable_log == True:
            if not os.path.isdir(dir_log_path):
                raise NotADirectoryError(f"{dir_log_path} is not a directory")

            self.make_log = MngLogFile(dir_log_path, "CanLogging.log",\
                                                log.DEBUG, "Can logging")  
    #------------------------
    # @connect
    #------------------------          
    @abstractmethod
    def connect(self, **kwargs):
        pass
    
    #------------------------
    # @disconnect
    #------------------------     
    @abstractmethod
    def disconnect(self):
        pass
    
    #------------------------
    # @send
    #------------------------     
    @abstractmethod
    def send(self, f_frame:StructCANMsg):
        pass

    #------------------------
    # @receive_poll
    #------------------------     
    @abstractmethod
    def receive_poll(self) ->StructCANMsg:
        pass
    
    #------------------------
    # receive_queue_start
    #------------------------     
    def receive_queue_start(self)->None:
        """
            @brief 
        """ 
        if not self.is_init:
            raise CanModuleNotInitError('Instance Not Init, please use Connect Method first')

        self._stop_rx_thread.clear()
        self._rx_thread = Thread(target= self._can_reader_cyclic, daemon=True)
        self._rx_thread.start()

    def reset_stats(self) -> None:
        self._stats = {
            "low_rx_total": 0,
            "low_queue_total": 0,
        }

    def get_stats(self) -> dict:
        return dict(self._stats)

    #------------------------
    # receive_queue_stop
    #------------------------     
    def receive_queue_stop(self) ->None:
        return self._stop_rx_thread.set()
    
    #------------------------
    # get_can_frame
    #------------------------     
    def get_can_frame(self, f_timeout:float=0.05)->StructCANMsg:
        try:
            msg, timestamp = self._receive_queue.get(timeout=f_timeout)
            return StructCANMsg(msg.ID, MsgType.CAN_MNGMT_MSG_STANDARD, msg.LEN, msg.DATA, int(timestamp.millis))
        except (Empty):
            return StructCANMsg()
                
    #------------------------
    # @flush
    #------------------------     
    @abstractmethod
    def flush(self)->None:
        pass

    #------------------------
    # default_error_handler
    #------------------------     
    def default_error_handler(self, status):
        print(f'[ERROR] : Can Error code -> {status}')

    #------------------------
    # _queue_rx_item
    #------------------------
    def _queue_rx_item(self, f_item) -> None:
        """Push one item in RX queue, dropping oldest on overflow."""
        try:
            self._receive_queue.put_nowait(f_item)
        except Full:
            try:
                self._receive_queue.get_nowait()
            except Empty:
                pass
            try:
                self._receive_queue.put_nowait(f_item)
            except Full:
                pass

    #------------------------
    # @_can_reader_cyclic
    #------------------------
    @abstractmethod
    def _can_reader_cyclic(self):
        pass

    #------------------------
    # _try_reconexion
    #------------------------
    def _try_reconexion(self, max_retries=5):
        """When a default occur, try to reconnect t othe target

        Args:
            max_tries (int, optional): _description_. Defaults to 5.
        """
        reconnect_delay = 5  # secondes
        print('[WARNING] : Ecu disconnected')
        self.disconnect()
        print(f"[INFO] : Try reconexion in  {reconnect_delay}s...")

        for _ in range(reconnect_delay * 10):
            if self._stop_rx_thread.is_set():
                return
            time.sleep(0.1)

        attempt = 0

        while not self._stop_rx_thread.is_set() and attempt < max_retries:
            try:
                self.connect()  # tente de rouvrir le port
                print("[INFO] : Successfully reconnected to ecu")
                return
            except (Exception):
                attempt += 1
                print(f"[WARNING] : Reconnexion failed (try {attempt}/{max_retries}), new try in 2 s...")
                time.sleep(2)

        self.error_cb_mngmt(CanMngmtError.ErrorTimeout)
        self._stop_rx_thread.set()
        print("Échec de reconnexion après plusieurs tentatives.")
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
