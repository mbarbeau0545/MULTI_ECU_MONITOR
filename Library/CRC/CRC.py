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
import sys
import os
from enum import IntEnum

#------------------------------------------------------------------------------
#                                       CONSTANT
#------------------------------------------------------------------------------

# CAUTION : Automatic generated code section: Start #

# CAUTION : Automatic generated code section: End #
#------------------------------------------------------------------------------
#                                       CLASS
#------------------------------------------------------------------------------
class CRC8Polynomial(IntEnum):
    STD = 0x07       # x⁸ + x⁴ + x³ + x² + 1
    ANSI = 0x1D      # x⁸ + x⁷ + x⁶ + x³ + x² + x + 1
    ITU = 0x83       # x⁸ + x⁷ + x + 1


class CRC16Polynomial(IntEnum):
    STD = 0x8005     # x¹⁶ + x¹⁵ + x² + 1
    ANSI = 0x11021   # x¹⁶ + x¹² + x⁵ + 1 (Note : 0x11021 > 16 bits, attention)
    ITU = 0x1021     # x¹⁶ + x¹² + x⁵ + 1


class CRC32Polynomial(IntEnum):
    ETH_ZIP_PNG = 0xEDB88320  # reversed polynomial used in Ethernet, ZIP, PNG
    CASTAGNOLI = 0x1EDC6F41
    KOOPMAN = 0x741B8CD7


class CRC8StartValue(IntEnum):
    STD = 0xFF
    ANSI = 0xFF
    ITU = 0xFF


class CRC16StartValue(IntEnum):
    STD = 0xFFFF
    ANSI = 0xFFFF
    ITU = 0xFFFF


class CRC32StartValue(IntEnum):
    ETH_ZIP_PNG = 0xFFFFFFFF
    CASTAGNOLI = 0xFFFFFFFF
    KOOPMAN = 0xFFFFFFFF

#--------------------------
# compute_crc8
#--------------------------
def compute_crc8(data: bytes,
                polynomial: CRC8Polynomial = CRC8Polynomial.STD,
                init_val: CRC8StartValue = CRC8StartValue.STD) -> int:
    crc = init_val
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc << 1) ^ polynomial if (crc & 0x80) else (crc << 1)
            crc &= 0xFF  # garder 8 bits
    return crc


#--------------------------
# compute_crc16
#--------------------------
def compute_crc16(  data: bytes,
                    polynomial: CRC16Polynomial = CRC16Polynomial.STD,
                    init_val: CRC16StartValue = CRC16StartValue.STD) -> int:
    crc = init_val
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            crc = (crc << 1) ^ polynomial if (crc & 0x8000) else (crc << 1)
            crc &= 0xFFFF  # garder 16 bits
    return crc

#--------------------------
# compute_crc32
#--------------------------
def compute_crc32(  data: bytes,
                    polynomial: CRC32Polynomial = CRC32Polynomial.ETH_ZIP_PNG,
                    init_val: CRC32StartValue = CRC32StartValue.ETH_ZIP_PNG) -> int:
    crc = init_val
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ polynomial
            else:
                crc >>= 1
            crc &= 0xFFFFFFFF  # garder 32 bits
    return ~crc & 0xFFFFFFFF  # inversion finale et garder 32 bits
#------------------------------------------------------------------------------
#                             FUNCTION IMPLMENTATION
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

