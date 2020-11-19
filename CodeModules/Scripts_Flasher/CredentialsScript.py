#!/usr/bin/env python

import subprocess
import glob
import os
import sys
from os.path import expanduser

sys.path.insert(1, './pystlink-master')

ERROR_INCOMPATIBLE_ID = 0x1
ERROR_DECRYPT_FILE = 0x2
ERROR_GENERATING_CREDENTIALS = 0x3
ERROR_DELETE_LINE = 0x4
ERROR_DELETE_FILE = 0x5
ERROR_FLASH_FIRMWARE = 0x6
ERROR_FLASH_CREDENTIALS = 0x7
ERROR_DEVICE_CONNECTION = 0x8


class CredentialsGenerator:

    def __init__(self):
        self.sfx_path = r".\sfxFlasher" + r"\SIGFOX_FLASHER.exe"
        self.AESd_path = r".\AES_Decrypt\AESd.exe"
        self.file_size = 0
        self.credential_ind = 0
        self.current_id = ' '
        self.home = expanduser("~")
        self.output_path = r".\output\\"
        self.END_EXECUTION = 0
        self.ERROR = 1
        self.ID = self.get_id_att()
        self.PAC = self.get_pac_att()
        self.pystlink_path = r".\pystlink-master\pystlink.py"
        self.tuple_error = (0, " ", False)
        self.status = (0, " ", False)
        self.decrypt_key = "b8f8754fb482bbfcfaa541b259639a2a"
        self.AESd_path = r".\AES_Decrypt\AESd.exe"
        self.compiler_path = r".\AES_Decrypt\AES_Decrypt.cpp"
        self.index = None

    def get_pac_att(self):
        line = self.read_id_pac_file()
        id_pac = self.get_id_pac(line)
        str_aux = id_pac.split(';')
        return str_aux[1].lstrip()

    def get_id_att(self):
        line = self.read_id_pac_file()
        id_pac = self.get_id_pac(line)
        str_aux = id_pac.split(';')
        return str_aux[0].lstrip()

    def get_txt_file_name(self):
        for file in glob.glob(r".\AES_Decrypt\*.txt"):
            if file != ".\AES_Decrypt\id_key_dec.txt":
                return file

    def get_id_pac(self, str_aux):
        id_pac_str = str_aux.split(';')
        id_pac = id_pac_str[0] + ';' + id_pac_str[1] + ';'
        return id_pac

    def get_pac(self):
        return self.PAC

    def read_id_pac_file(self):
        path = self.get_txt_file_name()

        with open(path) as fp:
            line = ' '
            while line:
                line = fp.readline()
                return line

    def read_key_file(self, line_id):
        path = r".\AES_Decrypt\id_key_dec.txt"

        cont = 0
        with open(path) as fp:
            line = ' '
            while line:
                line = fp.readline()
                if cont == line_id:
                    return line
                cont += 1

    def right_id(self, id):
        if id != self.current_id:
            return False
        return True

    def get_key(self, str_aux):
        str_key_aux = str_aux.split(' ')

        try:
            self.current_id = str_key_aux[0]
            key = str_key_aux[1]
            key = key.split('\n')
            key = key[0]
        except IndexError:
            return '!'

        return key

    def generate_credentials(self, id_pac_key, credential_file_name):
        if subprocess.call([self.sfx_path, id_pac_key, '-e', 'fixed', '-k', "4864C7667E64C66D8867E77A488C4471",
                            '-f', credential_file_name], close_fds=False):
            print("Error generating credentials!\n")
            return False

        return True

    def get_id(self):
        return self.ID

    def run_decrypt(self):
        print("Decrypting...\n")

        file_name = self.get_file_name()

        try:
            subprocess.call([self.AESd_path, self.decrypt_key, file_name, r".\AES_Decrypt\id_key_dec.txt"])
        except FileNotFoundError:
            self.compile_decryptor()
            if subprocess.call(
                    [self.AESd_path, self.decrypt_key, file_name, r".\AES_Decrypt\id_key_dec.txt"], close_fds=False):
                print("Error decrypting credentials! \n")
                return False

        return True

    def get_file_name(self):
        for file in glob.glob(r".\AES_Decrypt\*.bin"):
            return file

    def compile_decryptor(self):
        print("Compiling...\n")
        if subprocess.call(["gcc", self.compiler_path, "-o",  r".\AES_Decrypt\AESd"], close_fds=False):
            print("Error compiling AESd!\n")

    def get_line_id(self, id_key_file, id_pac_file):
        line_id = int(id_pac_file, 16) - int(id_key_file, 16)
        return line_id

    def get_id_key_file(self, id_key):
        str_key_aux = id_key.split(' ')
        return str_key_aux[0]

    def run_credentials_generator(self):
        print("\nGenerating credentials bin...\n")

        try:
            if not self.run_decrypt():
                print("Error running decrypt file!\n")
                self.tuple_error = (ERROR_DECRYPT_FILE, "Error running decrypt file!", True)
                return self.tuple_error

            line_key = self.read_key_file(0)  # read first line
            id_key_file = self.get_id_key_file(line_key)
            line_id = self.get_line_id(id_key_file, self.ID)

            line_key = self.read_key_file(line_id)
            key = self.get_key(line_key)
            key.rstrip()
        except IndexError:
            self.tuple_error = (0, "", False)
            return self.tuple_error

        if not self.right_id(self.ID):
            print("ID or PAC ERROR! Incompatible ID or PAC!\n")
            self.tuple_error = (ERROR_INCOMPATIBLE_ID, "ID or PAC ERROR! Incompatible ID or PAC!", True)
            return self.tuple_error
        elif key == '!':
            self.tuple_error = (0, "", False)
            return self.tuple_error

        id_pac = self.ID + ";" + self.PAC + ";"

        id_pac_key = id_pac + key + ';' + '0' + ';' + '0' + ';' + '0' + ';' + '0'
        credential_file_name = self.output_path + "credential_" + self.ID + ".bin"

        if not self.generate_credentials(id_pac_key, credential_file_name):
            self.tuple_error = (ERROR_GENERATING_CREDENTIALS, "Error generating credentials!", True)
            return self.tuple_error

        if not self.delete_file():
            self.tuple_error = (ERROR_DELETE_FILE, "Error deleting file!", True)
            return self.tuple_error

        self.delete_file()

        self.tuple_error = (0, "", False)
        print("credentials_generator completed!\n")
        return self.tuple_error

    def delete_line(self, file, line_str):

        try:
            with open(file, "r+") as f:
                d = f.readlines()
                f.seek(0)
                for i in d:
                    if i != line_str:
                        f.write(i)
                f.truncate()
            return True
        except:
            return False

    def delete_file(self):
        try:
            os.remove(r".\AES_Decrypt\id_key_dec.txt")
        except:
            return False

        return True

    def delete_line_process(self):
        print("Deleting ID and PAC line...\n")

        id_pac_file = self.get_txt_file_name()
        line_id = self.read_id_pac_file()
        if not self.delete_line(id_pac_file, line_id):
            self.tuple_error = (ERROR_DELETE_LINE, "Error deleting line!", True)
            return self.tuple_error

        self.tuple_error = (0, "", False)
        return self.tuple_error

    def flash_firmware(self, firm_file, index):
        self.index = str(int(index) + 3) if (index == '2') else index

        param = "flash:verify:0x08000000:" + firm_file

        if not self.connect_device():
            self.status = (ERROR_DEVICE_CONNECTION, "Device not connected!", True)
            return self.status

        print("Flashing firmware...")

        if subprocess.call(['python', self.pystlink_path, 'flash:Firmware', 'flash:erase', param,
                            '-n', self.index], close_fds=False):
            self.status = (ERROR_FLASH_FIRMWARE, "Error flashing firmware!", True)
            #reset_device()
            return self.status

        print("\nDone!\n")
        #reset_device()

        self.status = (0, "", False)
        return self.status

    def flash_credentials(self, credentials_file, index):
        self.index = str(int(index) + 3) if (index == '2') else index

        credentials_file = r".\output" + r'\\' + credentials_file

        param = "flash:verify:0x08080000:" + credentials_file

        if not self.connect_device():
            self.status = (ERROR_DEVICE_CONNECTION, "Device not connected!", True)
            return self.status

        print("Flashing credentials...")

        if subprocess.call(["python", self.pystlink_path, "flash:0x08080000", "flash:erase", param, '-n', self.index],
                           close_fds=False):
            self.status = (ERROR_FLASH_CREDENTIALS, "Error flashing credentials!", True)
            #reset_device()
            return self.status

        print("\nDone!\n")
        #reset_device()

        self.status = (0, "", False)
        return self.status

    def get_device_index(self):
        cnt = 1

        while cnt <= 8:
            self.index = str(cnt)
            if self.connect_device():
                return self.index
            cnt += 1

        return "0"

    def connect_device(self):
        path = self.pystlink_path

        try:
            if subprocess.call(["python", path, '-n', self.index], close_fds=False, timeout=1):
                return True
        except Exception or OSError:
            return False
        return True
