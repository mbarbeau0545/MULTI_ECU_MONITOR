"""
#  @file        SerialMngmt.py
#  @brief       Manager Serial Communication.
#  @details     Send/Receive send frame.\n
#
#  @author      mba
#  @date        jj/mm/yyyy
#  @version     1.0
"""
#------------------------------------------------------------------------------
#                                       IMPORT
#------------------------------------------------------------------------------
import time, os
from queue import Queue, Empty
import serial
from typing import Optional
import threading
from Library.ModuleLog import MngLogFile, log
from enum import IntEnum

#------------------------------------------------------------------------------
#                                       CONSTANT
#------------------------------------------------------------------------------
START_BYTES = [0xAA, 0x55]  
SRL_TIMEOUT = 5
# CAUTION : Automatic generated code section: Start #

# CAUTION : Automatic generated code section: End #
#------------------------------------------------------------------------------
#                                       CLASS
#------------------------------------------------------------------------------
class SerialError(IntEnum):
    SerialErrorTimeout = 0 # no msg received after x ms
    SerialErrorLost = 1 # gate close unexpectedly

from queue import Queue, Empty
import serial, threading, time
from typing import Optional

SRL_TIMEOUT = 5_000_000_000  # exemple: 5 secondes
START_BYTES = b"\xAA\x55"  # exemple à adapter


class SerialMngmt():
    def __init__(self, f_baudrate:int, 
                 f_port_com:str,
                 f_enable_log:bool = False, 
                 f_dirlog:str = "",
                 f_srl_err_cb = None):

        self._baudrate = f_baudrate
        self._port_com:str = f_port_com
        self._serial: Optional[serial.Serial]
        self._frame_size : int = 0
        self._receive_queue: Queue = Queue()  # contiendra (frame, timestamp)
        self._rx_thread: Optional[threading.Thread] = None
        self._stop_thread = threading.Event()
        self._buffer = bytearray()
        self.error_callback = f_srl_err_cb
        self._enable_log = f_enable_log
        self._last_received_time = 0
        self._start_time = 0

        if self._enable_log:
            if not os.path.isdir(f_dirlog):
                raise NotADirectoryError(f"{f_dirlog} is not a directory")

            self.make_log = MngLogFile(f_dirlog, "SerialLogging.log",\
                                                log.DEBUG, "Serial logging")  
    #--------------------------
    # open_serial_line
    #--------------------------
    def open_serial_line(self)->None:
        try:
            self._serial = serial.Serial(
                port=self._port_com,
                baudrate=self._baudrate,
                timeout=0.1
            )
        except Exception as e:
            raise Exception(f'Unable to start the serial line, error : {e}')


    #--------------------------
    # send_serial
    #--------------------------
    def send_serial(self, msg_id:int, payload:bytearray)-> None:
        if self._serial and self._serial.is_open:
            frame = bytearray()
            frame.append(START_BYTES[0])
            frame.append(START_BYTES[1])
            frame.append(msg_id)
            frame.extend(payload)
            self._serial.write(frame)
        else:
            raise RuntimeError("Serial port not configured or not open")


    #--------------------------
    # read_serial
    #--------------------------
    def read_serial(self)-> str:
        if self._serial and self._serial.in_waiting:
            return self._serial.read(self._serial.in_waiting).decode('utf-8')
        return ""


    #--------------------------
    # configure_reception
    #--------------------------
    def configure_reception(self, f_nbByte:int)->None:
        if not self._serial:
            raise RuntimeError("Serial port must be configured before reception")

        self._frame_size  = f_nbByte
        self._stop_thread.clear()
        self._rx_thread = threading.Thread(target=self.__perform_cyclic, daemon=True)
        self._rx_thread.start()
    

    #--------------------------
    # get_frame
    #--------------------------
    def get_frame(self, timeout: float = 0.0)->Optional[tuple[bytes, int]]:
        """
        Get one frame from the Queue

        Returns:
            Optional[tuple[bytes, float]]: (frame, timestamp en secondes)
        """
        try:
            return self._receive_queue.get(timeout=timeout)
        except Empty:
            return None
        

    #--------------------------
    # __perform_cyclic
    #--------------------------
    def __perform_cyclic(self):
        self._last_received_time = time.time_ns()
        buffer_log:str = ""
        cnt_buff_log:int = 0
        self._start_time = time.time_ns()

        while not self._stop_thread.is_set():
            try:
                if self._serial.in_waiting:
                    data = self._serial.read(self._serial.in_waiting)
                    if data:
                        self._last_received_time = time.time_ns()
                        self._buffer.extend(data)
                        buffer_log += self._extract_frames()
                         
                        if self._enable_log:
                            cnt_buff_log += 1
                            if cnt_buff_log > 3000:
                                self.make_log.LCF_SetMsgLog(log.INFO, buffer_log)
                                cnt_buff_log = 0
                                buffer_log = ""
                        else: 
                            buffer_log = ""

            except serial.SerialException as e:
                print(f"[ERROR] Serial port error: {e}")
                self.__try_serial_reco()
            except Exception as e:
                print(f"[ERROR] Unexpected error: {e}")
                self._stop_thread.set()

            if time.time_ns() - self._last_received_time > SRL_TIMEOUT:
                print("[WARNING] No data received for 5 seconds.")
                if self.error_callback:
                    self.error_callback(SerialError.SerialErrorTimeout)
                self._last_received_time = time.time_ns()

            time.sleep(0.01)


    #--------------------------
    # _find_start_bytes
    #--------------------------
    def _find_start_bytes(self):
        for i in range(len(self._buffer) - 1):
            if self._buffer[i] == START_BYTES[0] and self._buffer[i + 1] == START_BYTES[1]:
                return i
        return -1
    

    #--------------------------
    # _extract_frames
    #--------------------------
    def _extract_frames(self) ->str:

        retval_buffer = ""
        while len(self._buffer) >= self._frame_size:
            start_index = self._find_start_bytes()
            if start_index == -1:
                self._buffer.clear()
                break
            elif start_index > 0:
                del self._buffer[:start_index]

            if len(self._buffer) >= self._frame_size:
                frame = self._buffer[:self._frame_size]
                ts = time.time_ns()  # timestamp en nanoseconde
                retval_buffer = str((ts - self._start_time) / 1e6) + ' '
                retval_buffer += frame.hex()
                retval_buffer += "\n"
                self._receive_queue.put((bytes(frame), ts))
                del self._buffer[:self._frame_size]
            else:
                break
        return retval_buffer

    #--------------------------
    # stop
    #--------------------------
    def stop(self):
        """Stop the reception thread gracefully"""
        self._stop_thread.set()
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join()
        if self._serial:
            self._serial.close()

    #--------------------------
    # __try_serial_reco
    #--------------------------
    def __try_serial_reco(self, max_retries=5):
        """When port close from the other side, try to reconnect else
        call user callback
        """
        print(f"[ERROR] Serial port error")
        self._serial.close()  # fermer proprement
        reconnect_delay = 5  # secondes
        print(f"Reconnexion dans {reconnect_delay}s...")
        for _ in range(reconnect_delay * 10):
            if self._stop_thread.is_set():
                return
            time.sleep(0.1)

        attempt = 0
        while not self._stop_thread.is_set() and attempt < max_retries:
            try:
                self._serial.open()  # tente de rouvrir le port
                print("Port série reconnecté avec succès")
                return
            except serial.SerialException:
                attempt += 1
                print(f"Reconnexion échouée (tentative {attempt}/{max_retries}), nouvelle tentative dans 2s...")
                time.sleep(2)

        # Si on arrive ici, c’est que la reconnexion a échoué max_retries fois
        self._stop_thread.set()
        print("Échec de reconnexion après plusieurs tentatives.")
        if self.error_callback:
            self.error_callback(SerialError.SerialErrorLost)


#------------------------------------------------------------------------------
#                             FUNCTION IMPLMENTATION
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
#			                MAIN
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
#		                    END OF FILE
#------------------------------------------------------------------------------
#--------------------------
# Function_name
#--------------------------

"""
    @brief
    @details

    @params[in]
    @params[out]
    @retval
"""

