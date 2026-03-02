
"""
#  @file        Code_Generation.py
#  @brief       Allow user to generate automatic code from an Excel Array.\n
#  @details     Multiple Excel may be used to generate code in a same Script file
#               just used the Load function.\n
#               Script file has to contain the right balise target shown as below.\n
#               You dont't have to indicate Sheet from your Excel, We search in every sheet
#               The array name. For the rest read API function and the example at the end
#
#  @author      mba
#  @date        jj/mm/yyyy
#  @version     1.0
"""
# Le path pour écrire, le path du fichier Excel, la feuille du fichier Excel 
# Des fonctions pour écrire du code générique : Dict, list de list, list ...
# Une fonction où l'on donne en entrée une str et on l'écrit dans le fichiers 
# Une fonction pour foutre dans une list de list le tableau 
#------------------------------------------------------------------------------
#                                       IMPORT
#------------------------------------------------------------------------------
from typing import List
import openpyxl.workbook
import os

#------------------------------------------------------------------------------
#                                       DEFINE
#------------------------------------------------------------------------------

TARGET_START_LINE = "/* CAUTION : Automatic generated code section: Start */\n"
TARGET_END_LINE =   "/* CAUTION : Automatic generated code section: End */\n"

TARGET_T_START_LINE = "    /* CAUTION : Automatic generated code section: Start */\n"
TARGET_T_END_LINE =   "    /* CAUTION : Automatic generated code section: End */\n"

TARGET_T_ENUM_START_LINE = "    /* CAUTION : Automatic generated code section for Enum: Start */\n"
TARGET_T_ENUM_END_LINE =   "    /* CAUTION : Automatic generated code section for Enum: End */\n"

TARGET_T_VARIABLE_START_LINE = "    /* CAUTION : Automatic generated code section for Variable: Start */\n"
TARGET_VARIABLE_START_LINE = "/* CAUTION : Automatic generated code section for Variable: Start */\n"
TARGET_T_VARIABLE_END_LINE   = "    /* CAUTION : Automatic generated code section for Variable: End */\n"
TARGET_VARIABLE_END_LINE   = "/* CAUTION : Automatic generated code section for Variable: End */\n"
TARGET_T_STRUCT_START_LINE   = "    /* CAUTION : Automatic generated code section for Structure: Start */\n"
TARGET_T_STRUCT_END_LINE      ="    /* CAUTION : Automatic generated code section for Structure: End */\n"

TARGET_T_INCLUDE_START = "    /* CAUTION : Automatic generated code section for Include: Start */\n"
TARGET_T_INCLUDE_END   = "    /* CAUTION : Automatic generated code section for Include: End */\n"

TARGET_T_DEFINE_START = "    /* CAUTION : Automatic generated code section for Define: Start */\n"
TARGET_T_DEFINE_END   = "    /* CAUTION : Automatic generated code section for Define: End */\n"
#------------------------------------------------------------------------------
#                                       CLASS
#------------------------------------------------------------------------------
class LoadConfig_FromExcel():
    """
    @brief          Allow user to generate automatic code from an Excel Array
    @details  
    @retval
"""
    #--------------------------
    # __init__
    #--------------------------
    def __init__(self, ):
            self.excel_path = ""
            self.sheet_name = ""
            self.workbook = None
            self.sheets_astr = ""
            self.lines = None
            self.target_start_line = TARGET_START_LINE
            self.target_end_line = TARGET_END_LINE
            self.line_start_index = None
            self.line_end_index = None
            self.erase_previous_code_b = False
            self.ScriptList = {}
    #--------------------------
    # get_line_to_generate_code
    #--------------------------
    def get_line_to_generate_code(self, f_scriptPath_str:str):
        """
                @brief In order to write into script we have to know where the balise target are.\n
        """
        self.line_start_index = int(0)
        self.line_end_index   = int(0)
        try:
                with open(f_scriptPath_str, 'r') as file:
                    self.line = file.readlines()
        except:
            raise FileNotFoundError("[MakeList_FromExcelArray] : cannot open Script file")
        self.line_end_index = self.line.index(self.target_end_line)
        self.line_start_index = self.line.index(self.target_start_line)
        if(self.line_end_index and self.line_start_index) != int(0):
            f_path_balise = f_scriptPath_str + self.target_start_line
            if(f_path_balise not in self.ScriptList):
                self.ScriptList[f_path_balise] = False
            if(self.ScriptList[f_path_balise] == False):
                del self.line[self.line_start_index + 1:self.line_end_index]
                self.ScriptList[f_path_balise] = True
        else:
            raise ValueError(f"At least one of the target not found -> start {self.line_start_index} end -> {self.line_end_index}")
        return None
    #--------------------------
    # _extract_data_array
    #--------------------------
    def _extract_data_array(self, f_array):
        """
                @brief Store the array into data.\n
        """
        data_Array_a = []
        for index,line in enumerate(f_array):
            dataLine_a = []
            for cell in line:
                dataLine_a.append(cell.value)
            data_Array_a.append(dataLine_a)
        return data_Array_a
    #--------------------------
    # _write_into_file
    #--------------------------    
    def _write_into_file(self,f_generatedCode_str:str, f_scriptPath_str:str ):
        
        if(isinstance(f_scriptPath_str,str) == True  
           and os.path.isfile(f_scriptPath_str) == True):
            self.get_line_to_generate_code(f_scriptPath_str)
            self.line.insert(self.line_start_index + 1, f_generatedCode_str)
            with open(f_scriptPath_str, "w") as file:
                file.writelines(self.line)
        else:
            raise FileNotFoundError(f"[_write_into_file] : Param Invalid {f_scriptPath_str}")
    #--------------------------
    # change_target_balise
    #--------------------------
    def change_target_balise(self, f_targetStartLine:str,f_targetEndLine:str):
        if (isinstance(f_targetEndLine,str) and isinstance(f_targetStartLine,str)):
            self.target_start_line = f_targetStartLine
            self.target_end_line = f_targetEndLine
        else:
            raise TypeError
        
    #--------------------------
    # get_array_from_excel
    #--------------------------
    def get_array_from_excel(self, f_ArrayName_str):
        """
            @brief      Search the right array from Excel file
        """
        if(isinstance(f_ArrayName_str,str) == True):
            getArray_a = None
            self.workbook = openpyxl.load_workbook(self.excel_path, data_only=True)
            self.sheets_astr = self.workbook.sheetnames
            for sheet_name in self.sheets_astr:
                sheet = self.workbook[sheet_name]
                for array in sheet.tables.values():
                    if array.displayName == f_ArrayName_str:
                        try:
                            getArray_a =  (self._extract_data_array(sheet[array.ref]))
                        except:
                            raise ValueError("[GetArray_FromExcel] : Cannot extract array from Excel")
        else:
            raise ValueError("[GetArray_FromExcel] : param invalid")

        return getArray_a
    #--------------------------
    # load_excel_file
    #--------------------------
    def load_excel_file(self, f_excel_path:str):
        """
            @brief Store the Excel path where Excel Array are.\n
        """
        if(isinstance(f_excel_path, str) == True and os.path.isfile(f_excel_path) == True):
            self.excel_path = f_excel_path
        else:
            raise ValueError("[load_excel_file] param invalid or path nopt found")
        return
    #--------------------------
    # make_ennum_from_excelarray
    #--------------------------
    def make_ennum_from_excelarray(self,  f_ArrayName_str:str ,f_scriptPath_str:str, 
                                   f_spaceVariable_ui:int = 30, f_variableName_str:str = " ", 
                                   f_IsStringValue_b = True ):
        arrayEnum_a:List[List]= []
        generatedCode_str = ""
        arrayEnum_a = self._get_array_from_excel(f_ArrayName_str)[1:]
        if(arrayEnum_a != None and isinstance(f_variableName_str,str) and os.path.isfile(f_scriptPath_str)):
            generatedCode_str += "    typedef enum" + f' __{f_ArrayName_str if f_variableName_str == " " else f_variableName_str}\n' + '{\n'
            for idx, InstanceEnum_a in enumerate(arrayEnum_a):
                # Male enum with the first column
                # If value of enum is none and it's the first, initiliaze to 0 
                # If value of enum isn't None take the variable, else just put ","
                generatedCode_str += "\t" + str(InstanceEnum_a[0]).upper() 
                if(InstanceEnum_a[0] == None and idx == 0):
                    generatedCode_str += " " * (f_spaceVariable_ui - len(str(InstanceEnum_a[0]))) +  "= 0,\n"
                elif (InstanceEnum_a[0] == None):
                    generatedCode_str += ",\n"
                else:
                    generatedCode_str += "= " + str(int(InstanceEnum_a[1])) + ",\n"
            generatedCode_str +=  "\t}" + f'{f_ArrayName_str if f_variableName_str == " " else f_variableName_str};\n'
            self.change_target_balise(TARGET_T_ENUM_START_LINE,TARGET_T_ENUM_END_LINE)
            self._write_into_file(generatedCode_str, f_scriptPath_str)
            self.change_target_balise(TARGET_START_LINE,TARGET_END_LINE)
        else:
            raise TypeError("Arg Invalid")
        return
    #--------------------------
    # make_struct_from_excelarray
    #--------------------------
    def make_struct_from_excelarray(self,  f_ArrayName_str:str ,
                                    f_scriptPath_str:str, f_spaceVariable_ui:int = 30, 
                                    f_variableName_str:str = " ", f_IsStringValue_b = True ):
        arrayStruct_a:List[List]= []
        generatedCode_str = ""
        arrayStruct_a = self._get_array_from_excel(f_ArrayName_str)[1:]
        if(arrayStruct_a != None and isinstance(f_variableName_str,str) and os.path.isfile(f_scriptPath_str)):        
            generatedCode_str += "\ttypedef struct\n\t{\n"
            for arrayStruct_a in arrayStruct_a:
                if len(arrayStruct_a) != 2:
                    raise ValueError(f"Array Struct should have len 2 but have {len(arrayStruct_a)}")
                generatedCode_str += f"\t{arrayStruct_a[0]}" + " " * (f_spaceVariable_ui - len(str(arrayStruct_a[0]))) + f"{arrayStruct_a[1]};\n"
            generatedCode_str += "\t}" + f'{f_ArrayName_str if f_variableName_str == " " else f_variableName_str};\n'
            self.change_target_balise(TARGET_T_STRUCT_START_LINE,TARGET_T_STRUCT_END_LINE)
            self._write_into_file(generatedCode_str, f_scriptPath_str)
            self.change_target_balise(TARGET_START_LINE,TARGET_END_LINE)
        else:
            raise TypeError("Arg Invalid")
        return

    #--------------------------------
    # make_struct_from_excelarray
    #--------------------------------
    def make_enum_from_variable(self, f_root_enum:str, f_suffix_enum:List[str],
                                f_enum_name:str, f_first_val:int, 
                                f_enum_description:str = "", f_element_description:List[str] = [],
                                  f_IsHfile_b:bool = True) -> str:
        """
            Make a C enum typedef.\n
            make a enum from scratch with variable ->\n
            f_root_enum will be common for whole enum and completed with element 
            from the list f_suffix_enum, the name of the enum will be f_enum_name

            Args:
                f_IsHfile_b : wether or not the enum is destinate to an H file (add tabulation in this case)
            Returns: the string enum 
            Raises:
        """
        rc_enum: str = ""
        space: int = 0
        make_desc_b = False
        if not all((isinstance(f_enum_name,str), 
                   isinstance(f_first_val,int), 
                   isinstance(f_root_enum,str), 
                   isinstance(f_suffix_enum,list))):
            raise TypeError("Arg invalid")

        if f_element_description != []:
            make_desc_b = True
            if len(f_element_description) != len(f_suffix_enum):
                raise ValueError(f"Suffix list enum and enum description has not the same len, got {f_element_description} and {f_suffix_enum}")
        
        if(f_enum_description != ""):
            if f_IsHfile_b:
                rc_enum += "    "
            rc_enum += f"/**\n    * @brief {f_enum_description}.\n    */\n"
            
        if f_IsHfile_b:
            rc_enum += "    "
        rc_enum += "typedef enum\n    {\n"

        for idx, element in enumerate(f_suffix_enum):
            if f_IsHfile_b:
                rc_enum += "    "
            rc_enum += "    " + str(f_root_enum).upper() + "_" + str(element).upper()
            if(idx == 0):
                # set the value to the first enum
                rc_enum += f" = {str(int(f_first_val))},"
            else:
                rc_enum +=  ","
            if make_desc_b:
                rc_enum += " " * (25 - (len(str(element)) + ((6) if idx == 0 else (0))))
                rc_enum += f"/**< {f_element_description[idx]} */\n"
            else:
                rc_enum += "\n"

        if f_IsHfile_b:
            rc_enum += "    "
        rc_enum +=  "\n        " + f_root_enum + "_NB,\n"
        if f_IsHfile_b:
                rc_enum += "    "
        rc_enum += "} " + f_enum_name + ";\n\n"

        return rc_enum
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
    brief
    details

    args:
    returns:
    Raises:
"""

