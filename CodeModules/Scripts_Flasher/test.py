#!/usr/bin/env python

import subprocess
import sys

from CredentialsScript import CredentialsGenerator

class Test:

    def start(self):
        generator = CredentialsGenerator()

        index = generator.get_device_index()
        print("Index: " + index)
        #print(generator.run_credentials_generator())
        #print(generator.flash_credentials("test_credentials.bin", index)) #ir somando de 1 em 1 o nome do arquivo
        print(generator.flash_firmware("HT32SX_Test_FW.bin", index))
        #print(generator.delete_line_process()) #método para deletar a linha

if __name__ == '__main__':
    test = Test()
    test.start()
