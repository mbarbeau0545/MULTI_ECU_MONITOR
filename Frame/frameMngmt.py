"""
#  @file        main.py
#  @brief       Template_BriefDescription.
#  @details     TemplateDetailsDescription.\n
#
#  @author      mba
#  @date        jj/mm/yyyy
#  @version     1.0
"""
#------------------------------------------------------------------------------
#                                       IMPORT
#------------------------------------------------------------------------------
import sys, threading
from collections import deque
import os, time
import json
import re
from typing import Dict, List, Optional, Tuple
from queue import Queue, Empty


import importlib
from Protocole.CAN.Mngmt.CanMngmt import get_can_interface, DriverCanUsed,CANInterface
from Protocole.CAN.Mngmt.AbstractCAN import StructCANMsg, CanMngmtError, MsgType
from Protocole.SERIAL.SerialMngmt import SerialMngmt, SerialError, START_BYTES
from Library.ModuleLog import MngLogFile, log

#------------------------------------------------------------------------------
#                                       CONSTANT
#------------------------------------------------------------------------------
SYM_PATTERN_ENUM = r'(\d+)="([^"]+)"'
PATTERN_SIGNAL = re.compile(
    r"Sig=(\w+)\s+(\w+)\s+(\d+)"                         # nom, type, longueur
    r"(?:\s+(-m))?"                                      # encodage
    r"(?:\s+/f:([+-]?(?:\d+(?:\.\d*)?|\.\d+)))?"         # factor
    r"(?:\s+/o:([+-]?(?:\d+(?:\.\d*)?|\.\d+)))?"         # offset
    r"(?:\s+/max:(\d+))?"                                # max
    r"(?:\s+/e:(\w+))?"                                  # enum
)

PATTERN_SYM_ID = re.compile(
    r'ID=([0-9A-Fa-f]+)h\s*//\s*(\w+)\s*(.*)'
)
SYM_PATTERN_LEN = re.compile(r'Len=(\d+)')
SYM_PATTERN_SIG = re.compile(r'Sig=(\w+)\s+(\d+)')

DBC_SYM_PATTERN = re.compile(r'^BO_\s+(\d+)\s+(\w+):\s+(\d+)\s+\S+')
DBC_SIG_PATTERN = re.compile(r'^SG_\s+(\w+)\s+(\w+)\s*:\s*(\d+)\|(\d+)@(\d)([+-])\s+\(([^,]+),([^)]+)\)\s+\[([^|]+)\|([^\]]+)\]\s+"([^"]*)"\s+(\S+)$')
DBC_ENM_PATTERN = re.compile(r'^VAL_TABLE_\s+(\w+)\s+(\d+)\s+(.*);$')
DBC_ENM_VAL_PATTERN = re.compile(r'(\d+)\s+"([^"]+)"')
DBV_ENM_AFECT_PATTERN = re.compile(r'^VAL_\s+\d+\s+(\w+)\s+(\d+)')

MSG_TYPE_MAPPING = {
    'RECEIVE' : 'APPSIG_MSG_DIR_RX',
    'SEND' : 'APPSIG_MSG_DIR_TX',
    'SENDRECEIVE' : 'APPSIG_MSG_DIR_RX_TX',
}
# CAUTION : Automatic generated code section: Start #

# CAUTION : Automatic generated code section: End #
#------------------------------------------------------------------------------
#                                       CLASS
#------------------------------------------------------------------------------
class IdxSignal:
    lenght = 0
    enumlink = 1

class FrameMngmt():
    def __init__(self, f_prjcfg_file:str):
        self.prj_cfg_data = {}
        candriver:DriverCanUsed = DriverCanUsed.DrvPeak
        self._serial_istc:Optional[SerialMngmt] = None
        self._can_istc:Optional[CANInterface] = None

        if not os.path.isfile(f_prjcfg_file):
            raise FileNotFoundError(f'Signal Config file doest not exits {f_prjcfg_file}')
        
        with open(f_prjcfg_file, "r") as file:
            self.prj_cfg_data = json.load(file)

        try:
            self.sigcfg_file = self.prj_cfg_data["signal_cfg"]
            srl_baudrate:int = self.prj_cfg_data["serial_cfg"]["baudrate"]
            srl_protcom:str = self.prj_cfg_data["serial_cfg"]["port_com"]
            self._srl_frame_len = self.prj_cfg_data["serial_cfg"]["frame_len"]

            self._is_serial_enable:bool = self.prj_cfg_data["serial_cfg"]["is_enable"]
            self._is_can_enable:bool = self.prj_cfg_data["can_cfg"]["is_enable"]

            self._enable_can_log:bool = self.prj_cfg_data["can_cfg"]["enable_can_msg_logg"]
            self._enable_cansig_log:bool = self.prj_cfg_data["serial_cfg"]["enable_sig_logg"]
            self._enable_srl_log:bool = self.prj_cfg_data["serial_cfg"]["enable_srl_msg_logg"]
            self._enable_srlsig_log:bool = self.prj_cfg_data["serial_cfg"]["enable_sig_logg"]

            self._can_id_ignore:List[int] =  self.prj_cfg_data["can_cfg"]["id_to_ignore"]

            if self._is_can_enable:
                gate:str = self.prj_cfg_data["can_cfg"]["gate"]
                if gate.upper() == "PEAK":
                    candriver = DriverCanUsed.DrvPeak
                elif gate.upper() == "WAVESHARE":
                    candriver = DriverCanUsed.DrvWaveShare
                elif gate.upper() in ("PCSIM", "PC_SIM"):
                    candriver = DriverCanUsed.DrvPcSim
                else:
                    raise ValueError(f"{gate} gate for CAN not allowed. Allowed: PEAK, WAVESHARE, PCSIM")

        except (KeyError, TypeError, AttributeError) as e:
            raise Exception(f'An error occured while extracting config project -> {e}')       

        # signals maangment
        self.enum:Dict[str, List[List[int]]] = {}
        self.signals:Dict[str, Dict] = {}
        self.sig_value:Dict[str, Queue] = {}
        self.msg_sig_value:Dict[str, Queue] = {}
        self._pending_msg_updates_latest: Dict[str, Tuple[int, str, List]] = {}
        self._latest_sig_value: Dict[str, List] = {}
        self._latest_msg_sig_value: Dict[str, List] = {}
        self.symbol:Dict[str, Dict] = {}
        self.can_cnt_buff_log:int = 0
        self.srl_cnt_buff_log:int = 0
        self.list_id = {
            'SRL' : [],
            'CAN' : []
        }

        if self._is_can_enable:
            self._can_istc = get_can_interface( candriver,
                                            f_canlogging=self._enable_can_log,
                                            f_dirlog_path= self.prj_cfg_data["can_cfg"]["can_log_path"],
                                            f_error_cb= self.__error_can_cb)
        if self._enable_cansig_log:
            self.sigcan_log = MngLogFile( self.prj_cfg_data["can_cfg"]["sig_log_path"],
                                        "CanSigLogging.log",\
                                        log.DEBUG, "Signal logging")
            
        if self._is_serial_enable:
            self._serial_istc = SerialMngmt(srl_baudrate, 
                                        srl_protcom, 
                                        f_enable_log=self._enable_srl_log,
                                        f_dirlog=self.prj_cfg_data["serial_cfg"]["srl_log_path"],
                                        f_srl_err_cb=self.__error_serial_cb)
            
        if self._enable_srlsig_log:
            self.srlcan_log = MngLogFile( self.prj_cfg_data["serial_cfg"]["sig_log_path"],
                                        "SerialSigLogging.log",\
                                        log.DEBUG, "Signal logging")


        # thread maangment 
        self._srl_frame_thread: Optional[threading.Thread] = None
        self._can_frame_thread: Optional[threading.Thread] = None
        self._stop_srl_thread = threading.Event()
        self._stop_can_thread = threading.Event()
        self._start_time = time.time_ns()
        self._can_cyclic_rx_total = 0
        self._can_cyclic_processed_total = 0

        #---- extract signals enum and stuff ----#
        self.__extract_signal_cfg()
        self._build_symbol_indexes()

    def _build_symbol_indexes(self) -> None:
        self._symbol_by_can_id_exact: Dict[int, Dict] = {}
        self._symbol_by_can_id16: Dict[int, List[Dict]] = {}
        self._symbol_by_serial_id: Dict[int, Dict] = {}
        for _, sym in self.symbol.items():
            msg_id = sym.get("msg_id")
            if msg_id is None:
                continue
            try:
                msg_id_int = int(msg_id)
            except Exception:
                continue
            self._symbol_by_can_id_exact[msg_id_int] = sym
            low_id = msg_id_int & 0x0000FFFF
            if low_id not in self._symbol_by_can_id16:
                self._symbol_by_can_id16[low_id] = []
            self._symbol_by_can_id16[low_id].append(sym)
            self._symbol_by_serial_id[msg_id_int] = sym

    def _register_signal_sample(self, msg_id: int, signal_name: str, sample: List) -> None:
        if signal_name not in self.sig_value.keys():
            self.sig_value[signal_name] = Queue()

        msg_sig_name = str(msg_id) + signal_name
        if msg_sig_name not in self.msg_sig_value.keys():
            self.msg_sig_value[msg_sig_name] = Queue()

        # Keep queue compatibility but avoid backlog: store only latest sample.
        try:
            while True:
                self.msg_sig_value[msg_sig_name].get_nowait()
        except Empty:
            pass
        try:
            while True:
                self.sig_value[signal_name].get_nowait()
        except Empty:
            pass

        self.msg_sig_value[msg_sig_name].put(sample)
        self.sig_value[signal_name].put(sample)
        self._latest_sig_value[str(signal_name)] = sample
        self._latest_msg_sig_value[msg_sig_name] = sample
        self._pending_msg_updates_latest[msg_sig_name] = (int(msg_id), str(signal_name), sample)

    #--------------------------
    # get_signal_value
    #--------------------------
    def get_signal_value(self, f_signal: str) -> List[int]:
        """Get the Queue of values for a given signals.
        Args:
            f_signal (str): the name of the signals.
        Returns:
            List: a list of x element containing rawValue and ValueCompute [[1,4, timestamp], [5,20, timestamps]].
        Raises:
            KeyError: if the signals is not found.
        """
        result:List[int] = []
        latest = self._latest_sig_value.get(str(f_signal))
        if latest is not None:
            result.append(latest)
            return result

        sig_queue = self.sig_value.get(f_signal)
        if sig_queue is None:
            raise KeyError(f"{f_signal} does not exist in Signal Configuration")
        
        # Vide la queue
        try:
            while True:
                # get_nowait lÃ¨ve Empty si la queue est vide
                item = sig_queue.get_nowait()
                result.append(item)
        except Empty:
            pass
        
        return result
    
    def get_msg_signal_value(self, f_msg_id:str, f_signal: str) -> List[int]:
        """Get the Queue of values for a given signals.
        Args:
            f_msg_id (str): the id of the message suppsoively containing the signal.
            f_signal (str): the name of the signals.
        Returns:
            List: a list of x element containing rawValue and ValueCompute [[1,4, timestamp], [5,20, timestamps]].
        Raises:
            KeyError: if the signals is not found.
        """
        result:List[int] = []
        key_msg_sig = str(f_msg_id) + f_signal
        latest = self._latest_msg_sig_value.get(key_msg_sig)
        if latest is not None:
            result.append(latest)
            return result

        sig_queue = self.msg_sig_value.get(key_msg_sig)
        if sig_queue is None:
            raise KeyError(f"{key_msg_sig} does not exist in Signal Configuration")
        
        # Vide la queue
        try:
            while True:
                # get_nowait lÃ¨ve Empty si la queue est vide
                item = sig_queue.get_nowait()
                result.append(item)
        except Empty:
            pass
        
        return result

    def get_pending_msg_updates(self, f_max_items: int = 5000) -> List[Tuple[int, str, List]]:
        if f_max_items <= 0:
            return []

        keys = list(self._pending_msg_updates_latest.keys())
        if len(keys) == 0:
            return []
        selected = keys[:f_max_items]
        result = [self._pending_msg_updates_latest[k] for k in selected]
        for k in selected:
            self._pending_msg_updates_latest.pop(k, None)
        return result

    def get_pending_msg_updates_count(self) -> int:
        return int(len(self._pending_msg_updates_latest))

    def get_latest_signal_value(self, f_signal: str) -> Optional[List]:
        return self._latest_sig_value.get(str(f_signal))
    #--------------------------
    # send_signal_msg
    #--------------------------
    def send_signal_msg(self, f_sigvalue:Dict[str,int], f_sym_name:str= "" , f_mux_idx = 0)->None:

        """
        Encode et envoie un message en fonction des signaux

        param:
            f_sigvalue dictionnary with key : signal_name value, value to encode
            f_sym_name : the symbol name, if you know it pull it, and if you don't we will try to 
                            found it with the key from f_sigvalue
            f_mux_idx : index multiplexor, not use right now
        """
        # Trouver le symbole
        if f_sym_name == "" :
            for sym, sym_info in self.symbol.items():
                if set(f_sigvalue.keys()) == set(sym_info['signals']['0'].keys()):
                    f_sym_name = sym
                    break

        if f_sym_name not in self.symbol or f_sym_name == "":
            print(f"[ERROR] : Symbole {f_sym_name} inconnu")
            return

        symbol = self.symbol[f_sym_name]
        msg_id = int(str(symbol['msg_id']))

        signals = symbol['signals']['0']  # pas de mux pour l'instant

        # Payload vide (par ex. 8 octets)
        payload = bytearray(8)  # sans header/id/checksum

        for signal_name, start_bit in signals.items():
            if signal_name not in f_sigvalue:
                continue  # pas fourni

            sig_conf = self.signals.get(signal_name)
            if not sig_conf:
                print(f"[ERROR] : Config signal {signal_name} absente")
                continue

            length = sig_conf['length']
            encoding_flag = sig_conf.get('encoding', "little")
            factor = sig_conf.get('factor', 1)
            offset = sig_conf.get('offset', 0)
            # mapping 
            if encoding_flag.upper() == "MOTOROLA":
                encoding = "big"
            else:
                encoding = "little"
            # Appliquer lâ€™inverse du dÃ©codage
            eng_value = f_sigvalue[signal_name]
            raw_value = int((eng_value - offset) / factor)

            sample = [raw_value, eng_value, time.time_ns()]
            self._register_signal_sample(msg_id, signal_name, sample)

            self.__insert_bits(payload, raw_value, start_bit, length, encoding)

        
        if self._is_can_enable and self._can_istc is not None:
            can_struct = StructCANMsg(
                msg_id, 
                length=len(payload),
                msgType=MsgType.CAN_MNGMT_MSG_EXTENDED,
                data=list(payload)
            )
            self._can_istc.send(can_struct)
            print(f'[INFO] : Send threw can bus {payload.hex()}')
        elif self._is_serial_enable and self._serial_istc is not None:
                self._serial_istc.send_serial(msg_id, payload)
                print(f'[INFO] : Send threw serial bus {payload.hex()}')
        else:
            print("[ERROR] No Serial or CAN Interface ready")

        


    #--------------------------
    # send_signal_msg
    #--------------------------
    def get_symbol_list(self)->List[str]:
        """Get all symbol in a list
        """
        return [str(sym_name) for sym_name in self.symbol.keys()]
    #--------------------------
    # get_signal_value
    #--------------------------
    def get_signal_list(self) -> List[str]:
        """Get a list with all signals

        Args:
            f_signal (str): the signals
        Returns:
            List[str]: the list with all signals
        """
        
        return [str(signal_name) for signal_name in self.signals.keys()]

    
    #--------------------------
    # get_signal_value
    #--------------------------
    def get_signal_from_symbol(self, f_sym_name:str, f_idx_mux = 0) -> List[str]:
        """Get a list with signals from a certain msg
        """
        retval_list = []
        if f_sym_name in self.symbol.keys() and\
        str(f_idx_mux) in self.symbol['signals'].keys():
            retval_list = [signal for signal in self.symbol['signals'][f_idx_mux].keys()]

        return retval_list

    #--------------------------
    # get_signal_info_from_symbol
    #--------------------------
    def get_signal_info_from_symbol(self, f_sym_name:str, f_idx_mux:str='0')->Dict[str, int]:
        """get the name and lenght of signals in dicitonnary
        """
        retval_dict = {}
        if f_sym_name in self.symbol.keys() and\
        str(f_idx_mux) in self.symbol[f_sym_name]['signals'].keys():
            for signal_name in self.symbol[f_sym_name]['signals'][f_idx_mux].keys():
                retval_dict[signal_name] = self.signals[signal_name].copy()

        else:
            print('[ERROR] param invalid in get_signal_info_from_symbol')
        return retval_dict


    #--------------------------
    # get_signal_value
    #--------------------------
    def perform_cyclic(self)->None:
        """Start opening serial & can gate (depending on configuration)
        extract raw bufer from can & serial and interpret data to put it 
        into sig_values
        """
        if self._is_serial_enable:
            self._serial_istc.open_serial_line()
            self._serial_istc.configure_reception(f_nbByte=self._srl_frame_len)
            self._stop_srl_thread.clear()
            self._srl_frame_thread = threading.Thread(target=self._cyclic_serial_frame, daemon=True)
            self._srl_frame_thread.start()

        if self._is_can_enable:
            self._can_cyclic_rx_total = 0
            self._can_cyclic_processed_total = 0
            can_cfg = self.prj_cfg_data["can_cfg"]
            connect_kwargs = {
                "device_port": can_cfg["device_port"],
                "can_speed_bps": can_cfg["can_speed_bps"],
            }
            if "timeout_s" in can_cfg:
                connect_kwargs["timeout_s"] = can_cfg["timeout_s"]
            if "poll_sleep_s" in can_cfg:
                connect_kwargs["poll_sleep_s"] = can_cfg["poll_sleep_s"]
            if "max_pop_per_cycle" in can_cfg:
                connect_kwargs["max_pop_per_cycle"] = can_cfg["max_pop_per_cycle"]
            if "clear_can_tx_on_connect" in can_cfg:
                connect_kwargs["clear_can_tx_on_connect"] = can_cfg["clear_can_tx_on_connect"]

            self._can_istc.connect(**connect_kwargs)
            self._can_istc.flush()
            self._can_istc.reset_stats()
            self._can_istc.receive_queue_start()
            self._stop_can_thread.clear()
            self._can_frame_thread = threading.Thread(target=self._cyclic_can_frame, daemon=True)
            self._can_frame_thread.start()

        # idem can
    
    #--------------------------
    # unperform_cyclic
    #--------------------------
    def unperform_cyclic(self)->None:
        """Unperform cyclic frame analyzer
        """
        if self._is_serial_enable:
            self._serial_istc.stop()
            self._stop_srl_thread.set()

        if self._is_can_enable:
            self._can_istc.receive_queue_stop()
            self._can_istc.disconnect()
    #--------------------------
    # _cyclic_serial_frame
    #--------------------------
    def _cyclic_serial_frame(self)->None:
        """Interpret a frame and put the value into signals

        Args:
            bytes (bytes): frame bytes
            len_frame (int):len of the frame

        Raises:
        """
        cnt_buff_log:int = 0
        buffer_log:str = ''

        while not self._stop_srl_thread.is_set():
            srl_frame = self._serial_istc.get_frame(timeout=0.05)
            if srl_frame is not None:
                buffer_log += self.__decode_srl_frame(srl_frame)

                if self._enable_srl_log:
                    cnt_buff_log += 1
                    if cnt_buff_log > 1000:
                        self.srlcan_log.LCF_SetMsgLog(log.INFO, buffer_log)
                        buffer_log = ''
                        cnt_buff_log = 0
                else:
                    buffer_log = ""
            else:
                time.sleep(0.001)

    
    #--------------------------
    # _cyclic_serial_frame
    #--------------------------
    def _cyclic_can_frame(self)->None:
        """Interpret a frame and put the value into signals

        Args:
            bytes (bytes): frame bytes
            len_frame (int):len of the frame

        Raises:
        """
        cnt_buff_log:int = 0
        buffer_log:str = ''

        while not self._stop_can_thread.is_set():
            can_frame = self._can_istc.get_can_frame(f_timeout=0.005)

            if can_frame.data != []:
                self._can_cyclic_rx_total += 1

            if can_frame.data != [] and can_frame.id not in self._can_id_ignore:
                self._can_cyclic_processed_total += 1
                buffer_log += self.__decode_can_frame(can_frame)

                if self._enable_cansig_log:
                    cnt_buff_log += 1
                    if cnt_buff_log > 1000:
                        self.sigcan_log.LCF_SetMsgLog(log.INFO, buffer_log)
                        buffer_log = ''
                        cnt_buff_log = 0
                
            else:
                #print('got nothing')
                time.sleep(0.001)

    def get_can_runtime_stats(self) -> Dict[str, int]:
        low_stats = {"low_rx_total": 0, "low_queue_total": 0}
        if self._can_istc is not None:
            try:
                low_stats = self._can_istc.get_stats()
            except Exception:
                pass

        return {
            "low_rx_total": int(low_stats.get("low_rx_total", 0)),
            "low_queue_total": int(low_stats.get("low_queue_total", 0)),
            "cyclic_rx_total": int(self._can_cyclic_rx_total),
            "cyclic_processed_total": int(self._can_cyclic_processed_total),
        }
                

    #--------------------------
    # __decode_srl_frame
    #--------------------------
    def __decode_srl_frame(self, f_srl_frame:Tuple[bytes,int])->str:
        """Interpret a serial frame into signals value
        Args: 
            f_srl_frame (bytes); the frame to decode
        Raises:
        """
        buffer_log = ''

        srl_data, ts = f_srl_frame
        if len(srl_data) < self._srl_frame_len:
            print("[ERROR] : Trame trop courte")
            return ''
        # 3e octet = id (en hex string pour correspondre Ã  msg_id dans symbol)
        msg_id = f"{srl_data[2]:03X}"  # ex: '010' ou '020'

        # Recherche du symbole correspondant Ã  msg_id
        symbol = self._symbol_by_serial_id.get(int(msg_id, 16))

        if symbol is None:
            print(f"[ERROR] : Symbole inconnu pour msg_id {msg_id}")
            return ''

        # no mux use yet, take the idx mux '0'
        signals:Dict = symbol['signals']['0']  # dict signal_name -> bit position

        for signal_name, start_bit in signals.items():
            sig_conf = self.signals.get(signal_name)
            if not sig_conf:
                print(f"[ERROR] : Signal {signal_name} not configured")
                continue

            length = sig_conf['length']
            encoding = sig_conf['encoding']
            factor = sig_conf.get('factor', 1)
            offset = sig_conf.get('offset', 0)
            enum_name = sig_conf.get('enum')

            # Extraire la valeur brute du signals (bitfield)
            raw_value = self.__extract_bits(srl_data[3:], start_bit, length, encoding)

            # Si enum est dÃ©fini, traduire la valeur
            if enum_name and enum_name in self.enum:
                enum_map = {entry[0]: entry[1] for entry in self.enum[enum_name]}
                value = enum_map.get(raw_value, raw_value)  # sinon valeur brute

            else:
                # Appliquer facteur et offset
                value = raw_value * factor + offset

            # Stocker la valeur dans la queue associÃ©e
            sample = [raw_value, value, ts]
            self._register_signal_sample(int(msg_id, 16), signal_name, sample)

            buffer_log += f'{(ts - self._start_time) / 1e6} {signal_name} {raw_value} {value}\n'

        return buffer_log

    #--------------------------
    # __decode_can_frame
    #--------------------------
    def __decode_can_frame(self, f_can_frame:StructCANMsg)-> str:
        """Interpret a serial frame into signals value
        Args: 
            f_srl_frame (bytes); the frame to decode
        Raises:
        """
        msg_id = f_can_frame.id
        bufffer_log = ''
        # if int(msg_id) == 0x18FF0130:
        #     print(f"[DBG CAN RX] id=0x{msg_id:X} ts={f_can_frame.timestamp} dlc={f_can_frame.length} data={list(f_can_frame.data)}")
        # Recherche du symbole correspondant Ã  msg_id
        symbol = self._symbol_by_can_id_exact.get(int(msg_id))
        if symbol is None:
            candidates = self._symbol_by_can_id16.get(int(msg_id & 0x0000FFFF), [])
            if len(candidates) > 0:
                symbol = candidates[0]

        if symbol is None:
            pass#print(f"[ERROR] : Symbole inconnu pour msg_id {msg_id}")
            return bufffer_log

        
        raw_data = bytes([int(byte) for byte in list(f_can_frame.data)])


        #---- no mux use ----#
        if symbol['mux_info'] == {}:
            signals:Dict = symbol['signals']['0']
        #---- find value ----#
        else:
            idx_mux:int = self.__extract_bits(bytes(raw_data), 
                                                    symbol['mux_info']['start_bit'], 
                                                    symbol['mux_info']['length'],
                                                    symbol['mux_info']['encoding'])

            signals:Dict = symbol['signals'][str(idx_mux)]


        for signal_name, start_bit in signals.items():
            sig_conf = self.signals.get(signal_name)
            if not sig_conf:
                print(f"[ERROR] : Signal {signal_name} not configured")
                continue

            length = sig_conf['length']
            encoding = sig_conf['encoding']
            factor = sig_conf.get('factor', 1)
            offset = sig_conf.get('offset', 0)
            enum_name = sig_conf.get('enum')

            # Extraire la valeur brute du signals (bitfield)
            raw_value = self.__extract_bits(raw_data, start_bit, length, encoding)

            # Si enum est dÃ©fini, traduire la valeur
            if enum_name and enum_name in self.enum:
                enum_map = {entry[0]: entry[1] for entry in self.enum[enum_name]}
                value = enum_map.get(raw_value, raw_value)  # sinon valeur brute

            else:
                # Appliquer facteur et offset
                value = raw_value * factor + offset

            # Stocker la valeur dans la queue associÃ©e
            sample = [raw_value, value, f_can_frame.timestamp]
            self._register_signal_sample(msg_id, signal_name, sample)

            buffer_log = f"{f_can_frame.timestamp} 0x{msg_id:X} {signal_name} {raw_value} {value}\n"

        return buffer_log
    #--------------------------
    # __extract_bits
    #--------------------------
    def __extract_bits(self, data: bytes, start_bit: int, length: int, encoding: str) -> int:
        """
        Extrait un champ de bits d'une trame en fonction de son start_bit et de sa len.

        Args:
            data (bytes): trame binaire (ex: 8 octets CAN/SRL)
            start_bit (int): position du 1er bit LSB dans le champ (en bits)
            length (int): nombre total de bits Ã  extraire
            encoding (str): 'INTEL' (little endian) ou 'MOTOROLA' (big endian)

        Returns:
            int: valeur entiÃ¨re du champ extrait
        """
        bit_val = 0
        if len(data) != 8:
            raise ValueError(f'Error Expected 8 bytes of data')
        
        for i in range(length):
            if encoding.upper() == "INTEL":
                msg_bit = start_bit + i
            elif encoding.upper() == "MOTOROLA":
                # Algorithme identique Ã  celui de votre code C
                byte = start_bit // 8
                bit = start_bit % 8
                msg_bit = (byte * 8 + bit) - i
                msg_bit = ((7 - (msg_bit // 8)) * 8) + (msg_bit % 8)
            else:
                raise ValueError(f"Encodage non supportÃ©: {encoding}")

            byte_index = msg_bit // 8
            bit_in_byte = msg_bit % 8

            if byte_index >= len(data):
                break  # dÃ©passement de la trame -> ignorer

            bit = (data[byte_index] >> bit_in_byte) & 0x1
            bit_val |= (bit << i)

        return bit_val
    
    #--------------------------
    # __insert_bits
    #--------------------------
    def __insert_bits(self, buffer:bytearray, value:int, start_bit:int, length:int, encoding:str="little"):
        """InsÃ¨re une valeur entiÃ¨re dans le buffer Ã  la position spÃ©cifiÃ©e"""
        # Convertir buffer en entier global
        total_bits = len(buffer) * 8
        total_value = int.from_bytes(buffer, byteorder=encoding)

        mask = ((1 << length) - 1) << start_bit
        total_value &= ~mask  # clear bits
        total_value |= (value << start_bit) & mask

        # Remettre dans le buffer
        new_bytes = total_value.to_bytes(len(buffer), byteorder=encoding)
        for i in range(len(buffer)):
            buffer[i] = new_bytes[i]

    #--------------------------
    # __interpret_frame
    #--------------------------
    def __error_serial_cb(self, f_type_error:SerialError):
        """Management of serial line whenever an error occured
        """
        if f_type_error == SerialError.SerialErrorLost:
            self._stop_srl_thread.set()
            print("[ERROR] : Stopping serial thread in FrameMngmt")
        else:
            print('[WARNING] : Timeout occured in SerialMngmt, did not receive any frame...')
    
     #--------------------------
    # __interpret_frame
    #--------------------------
    def __error_can_cb(self, f_type_error:CanMngmtError):
        """Management of serial line whenever an error occured
        """
        if f_type_error == CanMngmtError.ErrorLost:
            self._stop_can_thread.set()
            print("[ERROR] : Stopping serial thread in FrameMngmt")
        else:
            print('[WARNING] : Timeout occured in SerialMngmt, did not receive any frame...')
    #--------------------------
    # __extract_signal_cfg
    #--------------------------
    def __extract_signal_cfg(self):
        """
            @brief get enum, signals, symbol from can signals config 
        """
 
        if not os.path.isfile(self.sigcfg_file):
            raise FileNotFoundError(f'Signal Config file doest not exits {self.sigcfg_file}')
        
        if str(self.sigcfg_file).endswith(".sym"):
            self.__sym_reader()

        elif str(self.sigcfg_file).endswith(".dbc"):
            self.__database_can_reader()

        else:
            raise Exception(f'Cannot found any function that interpret {self.sigcfg_file[str(self.sigcfg_file).index("."):]}')
    #--------------------------
    # __sym_reader
    #--------------------------
    def __sym_reader(self):
        """
            @brief get enum, signals, symbol from .sym file
        """
        current_read = 'NONE'
        waiting_for_timeout = False
        current_id = None
        current_type = None
        current_len = None
        current_symbol = None
        curr_idx_mux = '0'

        with open(self.sigcfg_file, 'r') as file:
            file_iter = iter(file)
            for line in file_iter:
                line = line.strip()

                if "ENUMS}" in line:
                    current_read = 'ENUMS'
                    continue
                elif "SIGNALS}" in line:
                    current_read = 'SIGNALS'
                    continue
                elif "SENDRECEIVE}" in line:
                    current_read = 'SENDRECEIVE'
                    continue
                elif "RECEIVE}" in line:
                    current_read = 'RECEIVE'
                    continue
                elif "SEND}" in line:
                    current_read = 'SEND'
                    continue

                match current_read:
                    case 'ENUMS':
                        if 'Enum=' in line:
                            # Ã‰tape 1 : rÃ©cupÃ©rer la ligne complÃ¨te entre parenthÃ¨ses
                            full_line = line.strip()
                            while ')' not in full_line:
                                next_line = next(file_iter).strip()  # file_iter = iter(fichier_lignes)
                                full_line += ' ' + next_line

                            # Ã‰tape 2 : extraire le nom de l'enum
                            start_index = full_line.index('Enum=') + len('Enum=')
                            end_index = full_line.index('(')
                            enum_name = full_line[start_index:end_index].strip()

                            # Ã‰tape 3 : extraire les paires index = "value"
                            resultats = re.findall(SYM_PATTERN_ENUM, full_line)
                            pairs = [[int(index), value] for index, value in resultats]

                            # Ã‰tape 4 : stocker
                            self.enum[enum_name] = pairs

                    case 'SIGNALS':
                        match = PATTERN_SIGNAL.match(line)
                        if match:
                            nom_signal    = match.group(1)
                            len_sig      = int(match.group(3))
                            encoding_flag = match.group(4)
                            factor        = float(match.group(5)) if match.group(5) else 1
                            offset        = int(match.group(6)) if match.group(6) else 0
                            # match.group(6) = max (non utilisÃ© ici)
                            enum_name     = match.group(8) if match.group(8) else None

                            encoding = "MOTOROLA" if encoding_flag else "INTEL"
                            self.sig_value[nom_signal] = Queue()

                            self.signals[nom_signal] = {
                                'length': len_sig,
                                'encoding': encoding,
                                'factor': factor,
                                'offset': offset,
                                'enum': enum_name,
                                'unit' : None
                            }
                        else:
                            print(f'[INFO] : APPSIG_Codegen : While in SIGNALS, no signals pattern in line: {line.strip()}')

                    case 'SEND' | 'RECEIVE' | 'SENDRECEIVE':
                        if line.startswith('['):  # Ex: [Symbol1]
                            current_symbol = line.strip().strip('[]')
                            self.symbol[current_symbol] = {
                                'msg_id': None,
                                'msg_len': None,
                                'msg_type': None,
                                'msg_direction': current_read,
                                'signals': {},
                                'mux_info' : {},
                                'timeout': 0,
                                'cycle_time': None  # <-- AjoutÃ© ici
                            }
                            waiting_for_timeout = True
                            continue

                        match_id = PATTERN_SYM_ID.match(line)
                        if match_id:
                            current_id = match_id.group(1)
                            current_type = match_id.group(2)

                            if current_type not in self.list_id:
                                self.list_id[current_type] = []

                            if current_id in self.list_id[current_type]:
                                raise ValueError(f'{current_id} already used in msg type {current_type}')
                            else:
                                self.list_id[current_type].append(current_id)

                            if current_symbol:
                                self.symbol[current_symbol]['msg_id'] = int(current_id,16)
                                self.symbol[current_symbol]['msg_type'] = current_type
                                # multi ecu managment 
                                if match_id.group(3) != "":
                                    multi_msg_dir = []
                                    for dir_cfg in str(match_id.group(3)).replace(" ", "").split(","):
                                        dir_value = str(dir_cfg.split(":")[1])
                                        if dir_value not in ["RECEIVE", "SEND", "SENDRECEIVE", "UNUSED"]:
                                            raise Exception(f'{dir_value} is unknwon expect ["RECEIVE", "SEND", "SENDRECEIVE"]')

                                        multi_msg_dir.append(dir_value)

                                    # on rÃ©ecrit la valeur de la direction
                                    self.symbol[current_symbol]['msg_direction'] = multi_msg_dir
                            continue

                        match_len = SYM_PATTERN_LEN.match(line)
                        if match_len:
                            current_len = int(match_len.group(1))
                            if current_symbol:
                                self.symbol[current_symbol]['msg_len'] = int(current_len)
                            continue

                        # Nouveau bloc : Timeout
                        if line.strip().lower().startswith("timeout="):
                            timeout_val = int(line.strip().split("=")[1].strip())
                            if current_symbol:
                                if timeout_val == 0:
                                    raise ValueError(f"Timeout cannot be 0 for symbol '{current_symbol}'")
                                self.symbol[current_symbol]['timeout'] = int(timeout_val)
                                waiting_for_timeout = False
                            continue

                        # Nouveau bloc : CycleTime
                        if line.strip().lower().startswith("cycletime="):
                            cycle_val = int(line.strip().split("=")[1].strip())
                            if current_symbol and (current_read == 'SEND' or current_read == 'SENDRECEIVE') :
                                if cycle_val == 0:
                                    raise ValueError(f"CycleTime cannot be 0 for symbol '{current_symbol}'")
                                self.symbol[current_symbol]['cycle_time'] = int(cycle_val)
                            continue

                        # Ligne signals
                        match_sig = SYM_PATTERN_SIG.match(line)
                        if match_sig:
                            signal_name = match_sig.group(1)
                            position = int(match_sig.group(2))

                            if current_symbol:
                                # VÃ©rifier si le signals est bien dÃ©fini
                                if signal_name not in self.signals:
                                    raise ValueError(f"Signal '{signal_name}' utilisÃ© par '{current_symbol}' non dÃ©fini dans SIGNALS")

                                new_start = position
                                new_length = self.signals[signal_name]['length']

                                try:
                                    for existing_signal, existing_start  in self.symbol[current_symbol]['signals'][curr_idx_mux].items():
                                        existing_length = self.signals[existing_signal]['length']

                                        new_end = new_start + new_length - 1
                                        existing_end = existing_start + existing_length - 1

                                        if not (new_end < existing_start or existing_end < new_start):
                                            raise ValueError(
                                                f"Conflit dans '{current_symbol}': signals '{signal_name}' (bits {new_start}-{new_end}) "
                                                f"chevauche '{existing_signal}' (bits {existing_start}-{existing_end})"
                                                )
                                except (KeyError):
                                    pass

                                # Pas de conflit, on ajoute le signals
                                if curr_idx_mux not in self.symbol[current_symbol]['signals'].keys():
                                    self.symbol[current_symbol]['signals'][curr_idx_mux] = {}

                                self.symbol[current_symbol]['signals'][curr_idx_mux][signal_name] = int(position)

                            continue

            # if current_symbol:
            #     sym = self.symbol[current_symbol]
            #     if sym['msg_direction'] == 'RECEIVE' or sym['msg_direction'] == 'SENDRECEIVE':
            #         if sym['timeout'] is None:
            #             raise ValueError(f"Missing Timeout for last symbol '{current_symbol}'")
            #     if sym['msg_direction'] == 'SEND' or sym['msg_direction'] == 'SENDRECEIVE':
            #         if sym['cycle_time'] is None:
            #             raise ValueError(f"Missing CycleTime for last symbol '{current_symbol}'")
    
    #--------------------------
    # __database_can_reader
    #--------------------------
    def __database_can_reader(self):
        """
            @brief get enum, signals, symbol from .sym file
        """
        idxenm_to_string = {}
        current_read:str = ''
        current_symbol:str =  ''
        with open(self.sigcfg_file, 'r') as file:
            lines = file.readlines()

        for line in lines:

            if str(line).upper().startswith('BO_ '):
                match = re.match(DBC_SYM_PATTERN, line.strip())

                if not match:
                    print(f'[INFO] : {line} does not match the symbol pattern')
                else:
                    sym_name = match.group(2)
                    msg_id = match.group(1)
                    msg_len = match.group(3)
                    self.symbol[sym_name] = {
                        "msg_id" : int(msg_id),
                        "msg_len" : int(msg_len),
                        "msg_type" : None,
                        "msg_direction" : None,
                        'signals': {},
                        'mux_info' : {},
                        'timeout': 0,
                        'cycle_time': None
                    }
                    current_symbol = sym_name

                current_read = 'SYMBOLE'
                continue

            elif str(line).upper().startswith('BU_:'):
                current_read = 'ENUM'
                continue

            elif str(line).upper().startswith('VAL_ '):
                current_read = 'AFFECT_ENUM'

            match current_read:
                case 'ENUM':
                    match = re.match(DBC_ENM_PATTERN, line.strip())
                    if not match:
                        continue
                    
                    else:
                        enum_name = match.group(1)
                        enum_idx = match.group(2)
                        table_val = match.group(3)
                        idxenm_to_string[str(enum_idx)] = enum_name
                        results = re.findall(DBC_ENM_VAL_PATTERN, table_val)
                        pairs = [[int(index), value] for index, value in results]
                        self.enum[enum_name] = pairs



                case 'AFFECT_ENUM':
                    match = re.match(DBV_ENM_AFECT_PATTERN, line.strip())
                    if not match:
                        print(f'[INFO] : {line} does not match the signal-enum affectation pattern')

                    else:
                        sig_name = match.group(1)
                        enum_idx = match.group(2)

                        if not sig_name in self.signals.keys():
                            print(f'[INFO] : Found an enum asoo but signal {sig_name} is not register')
                        else:
                            self.signals[sig_name]['enum'] = idxenm_to_string[str(enum_idx)]

                case 'SYMBOLE':
                    if "SG_" in line.upper():
                        match = re.match(DBC_SIG_PATTERN, line.strip())

                        if not match:
                            print(f'[INFO] : {line} does not match the signal pattern')
                        
                        else:
                            sig_name        = match.group(1)
                            idx_multiplexer = match.group(2)
                            start_bit       = match.group(3)
                            len_sig         = int(match.group(4))
                            factor          = int(match.group(7)) if match.group(7) else 1
                            offset          = int(match.group(8)) if match.group(8) else 0
                            encoding        = 'INTEL' if match.group(5) == "1" else 'MOTOROLA'
                            unit            = match.group(11)

                            #--- Info about the mux ----#
                            if str(idx_multiplexer).upper() == 'M':
                                self.symbol[current_symbol]['mux_info'] = {
                                    'length' : int(len_sig),
                                    'start_bit' : int(start_bit),
                                    'encoding': encoding
                                }
                            else:
                                #--- filled signal information ----#
                                if sig_name not in self.signals.keys():
                                    self.signals[sig_name] = {
                                        'length': int(len_sig),
                                        'encoding': encoding,
                                        'factor': int(factor),
                                        'offset': int(offset),
                                        'unit' : unit
                                    }
                                    self.sig_value[sig_name] = Queue()
                                #--- filled symbol information ----#
                                if idx_multiplexer == None:
                                    idx_multiplexer = '0'
                                else:
                                    idx_multiplexer = str(idx_multiplexer)[1:]

                                if idx_multiplexer not in self.symbol[current_symbol]['signals'].keys():

                                    self.symbol[current_symbol]['signals'][idx_multiplexer] = {}
                                
                                self.symbol[current_symbol]['signals'][idx_multiplexer][sig_name] = int(start_bit)


                case _:
                    pass

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


