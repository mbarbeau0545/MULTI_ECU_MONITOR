#-------------------------------------------------------------------
# Copyright (C) 2017 - KUHN SA - Electronics
#
# This document is KUHN SA property.
# It should not be reproduced in any medium or used in any way
# without prior written consent of KUHN SA
#-------------------------------------------------------------------
"""

    @file        WaveShareCanMngmt.py
    @brief       Offer an abstraction between Waveshare USB-CAN-A driver and CAN Mngmt
    @details     .\n

    @author      AUDMBA
    @date        11/02/2026
    @version     1.1
"""

#-------------------------------------------------------------------
#                     Import
#-------------------------------------------------------------------
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

import time
from dataclasses import dataclass
from typing import Optional

from Library.ModuleLog import log
from Library.Serialhelper.SerialHelper import find_port
from ..Drivers.WaveShare.Src.waveshare import (
    UsbCanAdapter,
    CANUSB_MODE,
    CANUSB_FRAME,
    SerialPortError,
)

from .AbstractCAN import (
    CANInterface,
    MsgType,
    StructCANMsg,
    CanModuleNotInitError,
    validate_config,
)

#-------------------------------------------------------------------
#                     Constants
#-------------------------------------------------------------------
DEBUG_MODE = False
SERIAL_BAUDRATE: int = UsbCanAdapter.CANUSB_TTY_BAUD_RATE_DEFAULT
MODE: CANUSB_MODE = CANUSB_MODE.NORMAL
FRAME_TYPE: CANUSB_FRAME = CANUSB_FRAME.EXTENDED

#-------------------------------------------------------------------
#                     Class
#-------------------------------------------------------------------
class DevicePortCfg(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    vid: str = Field(..., alias="Vid")
    pid: str = Field(..., alias="Pid")
    must_contain: Optional[str] = None

@dataclass
class WaveShareCanConfig:
    device_port: DevicePortCfg
    can_speed_bps: int



class WaveshareCanMngmt(CANInterface):
    """CANInterface implementation for Waveshare USB-CAN-A."""

    _FIXED_FRAME_LEN = 20

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.handle: UsbCanAdapter = UsbCanAdapter()
        self._config: Optional[WaveShareCanConfig] = None

    #------------------------
    # connect
    #------------------------
    def connect(self, **kwargs) -> None:
        self._config = WaveShareCanConfig(
            device_port=DevicePortCfg.model_validate(kwargs["device_port"]),
            can_speed_bps=int(kwargs["can_speed_bps"]),
        )

        com_port = find_port(
            int(self._config.device_port.vid, 16),              
            int(self._config.device_port.pid, 16),
            self._config.device_port.must_contain
        )         

        serial_dev = self.handle.adapter_init(device_port=com_port,
                                              baudrate=SERIAL_BAUDRATE)
        if serial_dev is None:
            raise ConnectionRefusedError('Unable to open Waveshare serial port')

        status = self.handle.command_settings(speed=self._config.can_speed_bps,
                                              mode=MODE,
                                              frame=FRAME_TYPE)
        if status < 0:
            raise ConnectionRefusedError(f'Waveshare CAN init failed (status={status})')

        self.is_init = True

    #------------------------
    # disconnect
    #------------------------
    def disconnect(self) -> None:
        if not self.is_init:
            raise CanModuleNotInitError('Instance Not Init, please use Connect Method first')

        self.receive_queue_stop()
        if self._rx_thread is not None:
            self._rx_thread.join(timeout=1.0)

        self.handle.adapter_close()
        self.is_init = False

    #------------------------
    # send
    #------------------------
    def send(self, f_frame: StructCANMsg) -> None:
        if not self.is_init:
            raise CanModuleNotInitError('Instance Not Init, please use Connect Method first')

        sent = False
        # Prefer adapter.inject_data_frame() if user updated it to actually inject on the bus.
        # Constrain it to a single emission using terminate_after.
        if hasattr(self.handle, 'inject_data_frame'):
            try:
                if f_frame.msgType == MsgType.CAN_MNGMT_MSG_STANDARD and 0 <= f_frame.id <= 0x7FF:
                    self.handle.program_running = True
                    self.handle.terminate_after = 1

                    hex_id = f"{f_frame.id:X}"
                    hex_data = ''.join(f"{b & 0xFF:02X}" for b in f_frame.data[:f_frame.length])

                    err = self.handle.inject_data_frame(hex_id, hex_data)
                    if err == 0:
                        sent = True
            except Exception:
                sent = False

        # Fallback: send a fixed 20-byte frame (reliable even if inject_data_frame is incomplete)
        if not sent:
            frame = self._build_fixed_20b_frame(f_frame)
            self.handle.frame_send(frame)

        if self.enable_log:
            try:
                self.make_log.LCF_SetMsgLog(
                    log.INFO,
                    "Snd  : 0x%03X %02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X" %
                    (
                        f_frame.id,
                        f_frame.data[0] if len(f_frame.data) > 0 else 0,
                        f_frame.data[1] if len(f_frame.data) > 1 else 0,
                        f_frame.data[2] if len(f_frame.data) > 2 else 0,
                        f_frame.data[3] if len(f_frame.data) > 3 else 0,
                        f_frame.data[4] if len(f_frame.data) > 4 else 0,
                        f_frame.data[5] if len(f_frame.data) > 5 else 0,
                        f_frame.data[6] if len(f_frame.data) > 6 else 0,
                        f_frame.data[7] if len(f_frame.data) > 7 else 0,
                    )
                )
            except Exception:
                pass

    def _build_fixed_20b_frame(self, f_frame: StructCANMsg) -> bytearray:
        # Fixed 20-byte Communication Protocol (as documented in waveshare.py)
        frame = bytearray(self._FIXED_FRAME_LEN)

        frame[0] = 0xAA
        frame[1] = 0x55
        frame[2] = 0x01  # Type: Data

        if f_frame.msgType == MsgType.CAN_MNGMT_MSG_EXTENDED:
            frame[3] = 0x02  # Extended
        else:
            frame[3] = 0x01  # Standard

        frame[4] = 0x01  # Data frame (not RTR)

        can_id = int(f_frame.id) & 0x1FFFFFFF

        frame[5] =  can_id        & 0xFF
        frame[6] = (can_id >> 8)  & 0xFF
        frame[7] = (can_id >> 16) & 0xFF
        frame[8] = (can_id >> 24) & 0xFF

        dlc = int(f_frame.length) & 0x0F
        if dlc > self._MC_DLC_8:
            dlc = self._MC_DLC_8
        frame[9] = dlc

        for idx in range(0, dlc):
            frame[10 + idx] = int(f_frame.data[idx]) & 0xFF

        frame[18] = 0x00  # Reserve
        frame[19] = self.handle.generate_checksum(frame[2:19])

        return frame

    #------------------------
    # receive_poll
    #------------------------
    def receive_poll(self) -> StructCANMsg:
        if not self.is_init:
            raise CanModuleNotInitError('Instance Not Init, please use Connect Method first')

        msg = StructCANMsg()

        try:
            frame = self._read_one_frame()
            if frame is not None:
                msg = self._parse_fixed_20b_frame(frame)
        except Exception:
            msg = StructCANMsg()

        return msg

    #------------------------
    # flush
    #------------------------
    def flush(self) -> None:
        if not self.is_init:
            raise CanModuleNotInitError('Instance Not Init, please use Connect Method first')

        # Best-effort: clear serial buffers if available.
        if self.handle.serial_device is not None:
            if hasattr(self.handle.serial_device, 'reset_input_buffer'):
                self.handle.serial_device.reset_input_buffer()
            if hasattr(self.handle.serial_device, 'reset_output_buffer'):
                self.handle.serial_device.reset_output_buffer()

        # Also clear software queue
        while not self._receive_queue.empty():
            try:
                self._receive_queue.get_nowait()
            except Exception:
                break

    #------------------------
    # _can_reader_cyclic
    #------------------------
    def _can_reader_cyclic(self) -> None:
        last_time_rec = time.time()

        while not self._stop_rx_thread.is_set():
            current_time = time.time()
            try:
                frame = self._read_one_frame()
            except Exception:
                frame = None

            if frame is None:
                time.sleep(0.001)
                continue

            last_time_rec = current_time
            msg = self._parse_fixed_20b_frame(frame)

            # Put a tuple to stay compatible with CANInterface.get_can_frame() signature,
            # but we override get_can_frame() below to return StructCANMsg directly.
            self._queue_rx_item((msg, msg.timestamp))

            if self.enable_log and msg.length > 0:
                try:
                    self.make_log.LCF_SetMsgLog(
                        log.INFO,
                        "Rcv  : 0x%03X %02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X" %
                        (
                            msg.id,
                            msg.data[0] if len(msg.data) > 0 else 0,
                            msg.data[1] if len(msg.data) > 1 else 0,
                            msg.data[2] if len(msg.data) > 2 else 0,
                            msg.data[3] if len(msg.data) > 3 else 0,
                            msg.data[4] if len(msg.data) > 4 else 0,
                            msg.data[5] if len(msg.data) > 5 else 0,
                            msg.data[6] if len(msg.data) > 6 else 0,
                            msg.data[7] if len(msg.data) > 7 else 0,
                        )
                    )
                except Exception:
                    pass

    #------------------------
    # get_can_frame (override)
    #------------------------
    def get_can_frame(self, f_timeout: float = 0.05) -> StructCANMsg:
        try:
            msg, _ts = self._receive_queue.get(timeout=f_timeout)
            return msg
        except Exception:
            return StructCANMsg()

    #------------------------
    # Internal RX helpers
    #------------------------
    def _read_one_frame(self) -> Optional[bytearray]:
        """Read one CAN frame from serial.

        The upstream driver frame_receive() is not usable for the fixed 20-byte protocol
        because it stops on the second header byte 0x55.
        So we implement a small robust receiver:

        - Search for 0xAA
        - Read next byte:
            * if 0x55 => fixed protocol, read remaining 18 bytes (total 20)
            * else => variable protocol, read until 0x55 end code (best-effort)
        """
        if self.handle.serial_device is None:
            return None

        ser = self.handle.serial_device

        # Find start 0xAA
        b = ser.read(1)
        if not b:
            return None
        while b and b[0] != 0xAA and not self._stop_rx_thread.is_set():
            b = ser.read(1)
            if not b:
                return None

        if self._stop_rx_thread.is_set():
            return None

        # Read next byte to discriminate protocol
        b2 = ser.read(1)
        if not b2:
            return None

        frame = bytearray()
        frame.append(0xAA)
        frame.append(b2[0])

        if b2[0] == 0x55:
            # Fixed protocol: read remaining bytes
            rest = ser.read(self._FIXED_FRAME_LEN - 2)
            if rest and len(rest) == (self._FIXED_FRAME_LEN - 2):
                frame.extend(rest)
                return frame
            return None

        # Variable protocol: read until 0x55 end code (max 32 bytes)
        max_len = 32
        while len(frame) < max_len and not self._stop_rx_thread.is_set():
            bn = ser.read(1)
            if not bn:
                break
            frame.append(bn[0])
            if bn[0] == 0x55:
                break

        return frame

    def _parse_fixed_20b_frame(self, frame: bytearray) -> StructCANMsg:
        """
        Parse Waveshare USB-CAN-A frames.
        Supports:
            - Variable length:  AA | Type | ID(2/4 LE) | Data(0..8) | 55
            - Fixed 20 bytes:   AA 55 | TYPE | FrameType | FrameFormat | ID(4 LE) | DLC | D0..D7 | 00 | checksum
        """
        msg = StructCANMsg()

        if frame is None or len(frame) < 4:
            return msg

        # ---------- Variable-length protocol ----------
        # AA | type | ... | 55
        if frame[0] == 0xAA and frame[-1] == 0x55 and not (len(frame) >= self._FIXED_FRAME_LEN and frame[1] == 0x55):
            ftype = frame[1]
            is_ext = (ftype & 0x20) != 0
            # is_rtr = (ftype & 0x10) != 0  # dispo si vous voulez le gérer
            dlc = int(ftype & 0x0F)
            if dlc > self._MC_DLC_8:
                dlc = self._MC_DLC_8

            if is_ext:
                id_len = 4
                id_mask = 0x1FFFFFFF
            else:
                id_len = 2
                id_mask = 0x7FF

            min_len = 1 + 1 + id_len + dlc + 1
            if len(frame) < min_len:
                return msg

            idx_id = 2
            idx_data = idx_id + id_len

            # ID little-endian
            can_id = 0
            for i in range(id_len):
                can_id |= int(frame[idx_id + i]) << (8 * i)
            can_id &= id_mask

            data = [int(frame[idx_data + i]) & 0xFF for i in range(dlc)]

            msg_type = MsgType.CAN_MNGMT_MSG_EXTENDED if is_ext else MsgType.CAN_MNGMT_MSG_STANDARD
            msg = StructCANMsg(can_id, msg_type, dlc, data, int(time.time() * 1000))
            return msg

        # ---------- Fixed 20-byte protocol ----------
        if len(frame) < self._FIXED_FRAME_LEN:
            return msg

        if frame[0] != 0xAA or frame[1] != 0x55:
            return msg

        checksum = frame[19]
        expected = self.handle.generate_checksum(frame[2:19])
        if checksum != expected:
            return msg

        frame_type = frame[3]  # 0x01 std, 0x02 ext

        # ID little-endian (cf. exemples Waveshare)
        can_id = (
            (int(frame[5]) << 0) |
            (int(frame[6]) << 8) |
            (int(frame[7]) << 16) |
            (int(frame[8]) << 24)
        )

        dlc = int(frame[9]) & 0x0F
        if dlc > self._MC_DLC_8:
            dlc = self._MC_DLC_8

        data = [int(frame[10 + i]) & 0xFF for i in range(dlc)]

        msg_type = MsgType.CAN_MNGMT_MSG_EXTENDED if frame_type == 0x02 else MsgType.CAN_MNGMT_MSG_STANDARD
        msg = StructCANMsg(can_id & (0x1FFFFFFF if msg_type == MsgType.CAN_MNGMT_MSG_EXTENDED else 0x7FF),
                        msg_type,
                        dlc,
                        data,
                        int(time.time() * 1000))
        return msg
