import time
import lib.stm32

# Stm32 L0 and L1 programming

firm_size = 0

class Flash():
    PECR_OFFSET       = 0x04
    PEKEYR_OFFSET     = 0x0c
    PRGKEYR_OFFSET    = 0x10
    OPTKEYR_OFFSET    = 0x14
    SR_OFFSET         = 0x18
    OPTR_OFFSET       = 0x1C

    STM32L0_NVM_PHY   = 0x40022000
    STM32L1_NVM_PHY   = 0x40023c00
    STM32_NVM_PEKEY1  = 0x89abcdef
    STM32_NVM_PEKEY2  = 0x02030405
    STM32_NVM_PRGKEY1 = 0x8c9daebf
    STM32_NVM_PRGKEY2 = 0x13141516

    PECR_PELOCK      = 1 <<  0
    PECR_PRGLOCK     = 1 <<  1
    PECR_PRG         = 1 <<  3
    PECR_ERASE       = 1 <<  9
    PECR_FPRG        = 1 << 10
    WPRMOD           = 0 << 8 #DISABLE

    SR_BSY           = 1 <<  0
    SR_EOP           = 1 <<  1
    SR_WRPERR        = 1 <<  8
    SR_PGAERR        = 1 <<  9
    SR_SIZERR        = 1 << 10

    OB_WRP_AllPages = 0x0000FFFF
    WRP_MASK_LOW    = 0x0000FFFF
    WRP_FINAL_MASK  = 0xFFFF0000
    OB_BASE         = 0x1FF80000

    SR_ERROR_MASK = SR_WRPERR | SR_PGAERR | SR_SIZERR

    def __init__(self, driver, stlink, dbg):
        self._driver = driver
        self._stlink = stlink
        self._dbg = dbg
        self._page_size = 2048
        #use core id to find out if L0 or L1
        if  stlink._coreid == 0xbc11477:
            self._nvm = Flash.STM32L0_NVM_PHY
            self._page_size = 128
        else:
            self._nvm = Flash.STM32L1_NVM_PHY
            self._page_size = 256
        self.unlock()

    def clear_sr(self):
        # clear errors
        sr = self._stlink.get_debugreg32(self._nvm + Flash.SR_OFFSET)
        self._stlink.set_debugreg32(self._nvm + Flash.SR_OFFSET, sr)

    def configWRP(self):
        self._stlink.set_debugreg32(self._nvm + Flash.OPTR_OFFSET, Flash.WPRMOD)
        self._stlink.get_debugreg32(self._nvm + Flash.OPTR_OFFSET)

    def unlock(self):
        self._dbg.debug('unlock')
        self._driver.core_reset_halt()
        self.wait_busy(0.01)
        self.clear_sr()
        # Lock first. Double unlock results in error!

        self.configWRP()

        self._stlink.set_debugreg32(self._nvm + Flash.PECR_OFFSET,
                                    Flash.PECR_PELOCK)
        pecr = self._stlink.get_debugreg32(self._nvm + Flash.PECR_OFFSET)

        while (pecr & Flash.PECR_PELOCK) == 0:
            self._stlink.set_debugreg32(self._nvm + Flash.PECR_OFFSET,
                                        Flash.PECR_PELOCK)
            pecr = self._stlink.get_debugreg32(self._nvm + Flash.PECR_OFFSET)

        if (pecr & Flash.PECR_PELOCK) != 0:
            # unlock keys
            self._stlink.set_debugreg32(self._nvm + Flash.PEKEYR_OFFSET,
                                        Flash.STM32_NVM_PEKEY1)
            self._stlink.set_debugreg32(self._nvm + Flash.PEKEYR_OFFSET,
                                        Flash.STM32_NVM_PEKEY2)
            pecr = self._stlink.get_debugreg32(self._nvm + Flash.PECR_OFFSET)
        else :
            raise lib.stlinkex.StlinkException(
                'Unexpected unlock behaviour! FLASH_CR 0x%08x' % pecr)
        # check if programing was unlocked
        if pecr & Flash.PECR_PELOCK:
            raise lib.stlinkex.StlinkException(
                'Error unlocking FLASH_CR: 0x%08x. Reset!' % pecr)

    def lock(self):
        self._stlink.set_debugreg32(self._nvm + Flash.PECR_OFFSET,
                                    Flash.PECR_PELOCK)
        self._driver.core_reset_halt()

    def prg_unlock(self):
        pecr = self._stlink.get_debugreg32(self._nvm + Flash.PECR_OFFSET)
        if not pecr & Flash.PECR_PRGLOCK:
            return
        if pecr & Flash.PECR_PELOCK:
            raise lib.stlinkex.StlinkException('PELOCK still set: %08x' % pecr)
        # unlock keys
        self._stlink.set_debugreg32(self._nvm + Flash.PRGKEYR_OFFSET,
                                    Flash.STM32_NVM_PRGKEY1)
        self._stlink.set_debugreg32(self._nvm + Flash.PRGKEYR_OFFSET,
                                    Flash.STM32_NVM_PRGKEY2)
        pecr = self._stlink.get_debugreg32(self._nvm + Flash.PECR_OFFSET)
        if pecr & Flash.PECR_PRGLOCK:
            raise lib.stlinkex.StlinkException('PRGLOCK still set: %08x' % pecr)

    def erase_pages(self, addr, size):
        self._dbg.verbose('erase_pages from addr 0x%08x for %d byte' %
                          (addr, size))
        erase_addr =   addr         & ~(self._page_size - 1)

        last_addr  =  (addr + size + self._page_size - 1) &\
                        ~(self._page_size - 1)

        self._dbg.bargraph_start('Erasing FLASH', value_min=erase_addr,
                                 value_max=last_addr)
        self.prg_unlock()
        pecr = Flash.PECR_PRG | Flash.PECR_ERASE
        self._stlink.set_debugreg32(self._nvm + Flash.PECR_OFFSET, pecr)

        while erase_addr < last_addr:
            self._stlink.set_debugreg32(erase_addr, 0)
            self.wait_busy(0.01)
            erase_addr += self._page_size
            #erase_addr += 4
            self._dbg.bargraph_update(value=erase_addr)
        self._dbg.bargraph_done()
        self._stlink.set_debugreg32(self._nvm + Flash.PECR_OFFSET, 0)

    def eeprom_erase_pages(self, addr, size):
        self._dbg.verbose('erase_pages from addr 0x%08x for %d byte' %
                          (addr, size))
        erase_addr =   addr         & ~(self._page_size - 1)

        last_addr  = addr + size

        self._dbg.bargraph_start('Erasing EEPROM', value_min=erase_addr,
                                 value_max=last_addr)
        self.prg_unlock()
        pecr = Flash.PECR_PRG | Flash.PECR_ERASE
        self._stlink.set_debugreg32(self._nvm + Flash.PECR_OFFSET, pecr)

        while erase_addr < last_addr:
            self._stlink.set_debugreg32(erase_addr, 0)
            self.wait_busy(0.01)
            #erase_addr += self._page_size
            erase_addr += 4
            self._dbg.bargraph_update(value=erase_addr)
        self._dbg.bargraph_done()
        self._stlink.set_debugreg32(self._nvm + Flash.PECR_OFFSET, 0)

    def wait_busy(self, wait_time, bargraph_msg=None, check_eop=False):
        end_time = time.time() + wait_time * 10.5
        if bargraph_msg:
            self._dbg.bargraph_start(bargraph_msg, value_min=time.time(),
                                     value_max=time.time() + wait_time)
        while time.time() < end_time:
            if bargraph_msg:
                self._dbg.bargraph_update(value=time.time())
            status = self._stlink.get_debugreg32(self._nvm + Flash.SR_OFFSET)
            if not status & (Flash.SR_BSY | (check_eop & Flash.SR_EOP)) :
                self.end_of_operation(status)
                if bargraph_msg:
                    self._dbg.bargraph_done()
                if check_eop:
                    self._stlink.set_debugreg32(self._nvm + Flash.SR_OFFSET,
                                                 Flash.SR_EOP)
                return
            time.sleep(wait_time / 20)
        raise lib.stlinkex.StlinkException('Operation timeout')

    def end_of_operation(self, status):
        if status & Flash.SR_ERROR_MASK:
            raise lib.stlinkex.StlinkException(
                'Error writing FLASH with status (FLASH_SR) %08x' % status)

class Stm32L0(lib.stm32.Stm32):
    flash_size = 64*1024

    def flash_erase_sector(self, addr, size):
        flash = Flash(self, self._stlink, self._dbg)

        #flash.configWRP()
        flash.erase_pages(addr, size)
        flash.lock()

    def eeprom_erase_sector(self, addr, size):
        flash = Flash(self, self._stlink, self._dbg)

        flash.eeprom_erase_pages(addr, size)
        flash.lock()

    def flash_erase_all(self):
        # Mass erase is only possible by setting and removing flash
        # write protection. This will also erase EEPROM!
        # Use page erase instead

        self._dbg.debug('Stm32L0.flash_erase_all')

        flash = Flash(self, self._stlink, self._dbg)

        flash.erase_pages(lib.stm32.Stm32.FLASH_START, self.flash_size * 1024);
        flash.lock()

    def configSize(self, size):
        global firm_size

        firm_size = size

        if (firm_size % 2) != 0:
            firm_size += 1

    def eeprom_write(self, addr, data, erase=False, verify=False,
                    erase_sizes=None):
            global firm_size

            if addr is None:
                addr = self.FLASH_START
            self._dbg.debug(
                'Stm32l4.flash_write '
                '(%s, [data:%dBytes], erase=%s, verify=%s, erase_sizes=%s)'
                % (addr, len(data), erase, verify, erase_sizes))
            if addr % 4:
                raise lib.stlinkex.StlinkException('Start address is not aligned to word')

            flash = Flash(self, self._stlink, self._dbg)
            if erase:
                if erase_sizes:
                    flash.erase_pages(addr, len(data))
                else:
                    flash.erase_all()

            self._dbg.bargraph_start('Writing EEPROM', value_min=addr,
                                     value_max=addr + len(data))
            flash.unlock()
            flash.prg_unlock()
            datablock = data
            data_addr = addr
            block = datablock
            while len(datablock):
                size = 0
                if data_addr & ((flash._page_size >> 1) - 1):
                    # not half page aligned
                    size = data_addr & ((flash._page_size >> 1) - 1)
                    size = (flash._page_size >> 1) - size
                if len(datablock) < (flash._page_size >> 1):
                    # remainder not full half page
                    size = len(datablock)
                    self.configSize(size)
                    size = firm_size

                while size:
                    block = datablock[:4]
                    datablock = datablock[4:]
                    try:
                        if max(block) != 0:
                            self._stlink.set_mem32(data_addr, block)

                    except ValueError:
                        return

                    data_addr += 4
                    size -= 4
                    self._dbg.bargraph_update(value=data_addr)
                    flash.wait_busy(0.005, check_eop=True)
                pecr = Flash.PECR_FPRG | Flash.PECR_PRG
                self._stlink.set_debugreg32(flash._nvm + Flash.PECR_OFFSET, pecr)
                while len(datablock) >= (flash._page_size >> 1):
                    #block = datablock[:(flash._page_size >> 1)]
                    block = datablock[:4]
                    datablock = datablock[4:]
                    if max(block) != 0:
                        self._stlink.set_mem32(data_addr, block)

                    data_addr += 4
                    self._dbg.bargraph_update(value=data_addr)
                    flash.wait_busy(0.005, check_eop=True)
                self._stlink.set_debugreg32(flash._nvm + Flash.PECR_OFFSET, 0)
            flash.lock()
            self._dbg.bargraph_done()
            if verify:
                self._dbg.bargraph_start('Verify EEPROM ', value_min=addr,
                                         value_max=addr + len(data))
                while (data):
                    block = data[:4]
                    data = data[4:]
                    time.sleep(0.001)  # FIXME: First read give wrong result w/o delay
                    cblock = self._stlink.get_mem32(addr, len(block))
                    # if block != cblock:
                    # raise lib.stlinkex.StlinkException (
                    #     'Verify error at block address: 0x%08x' % addr)
                    addr += len(block)
                    self._dbg.bargraph_update(value=addr)
                self._dbg.bargraph_done()

    def flash_write(self, addr, data, erase=False, verify=False,
                    erase_sizes=None):
        global firm_size

        if addr is None:
            addr = self.FLASH_START
        self._dbg.debug(
            'Stm32l4.flash_write '
            '(%s, [data:%dBytes], erase=%s, verify=%s, erase_sizes=%s)'
            % (addr, len(data), erase, verify, erase_sizes))
        if addr % 4:
            raise lib.stlinkex.StlinkException('Start address is not aligned to word')

        flash = Flash(self, self._stlink, self._dbg)
        if erase:
            if erase_sizes:
                flash.erase_pages(addr, len(data))
            else:
                flash.erase_all()

        self._dbg.bargraph_start('Writing FLASH', value_min=addr,
                                 value_max=addr + len(data))
        flash.unlock()
        flash.prg_unlock()
        datablock = data
        data_addr = addr
        block = datablock
        while len(datablock):
            size = 0
            if data_addr & ((flash._page_size >> 1) -1):
                # not half page aligned
                size = data_addr & ((flash._page_size >> 1) -1)
                size = (flash._page_size >> 1) - size
            if len(datablock) < (flash._page_size >> 1):
                # remainder not full half page
                size = len(datablock)
                self.configSize(size)

                size = firm_size

            while size:
                block = datablock[:4]
                datablock = datablock[4:]
                try:
                    if max(block) != 0:
                        self._stlink.set_mem32(data_addr, block)
                except ValueError:
                    return
                data_addr += 4
                size -= 4
                self._dbg.bargraph_update(value=data_addr)
                flash.wait_busy(0.005, check_eop=True)
            pecr = Flash.PECR_FPRG | Flash.PECR_PRG
            self._stlink.set_debugreg32(flash._nvm + Flash.PECR_OFFSET, pecr)
            while len(datablock) >= (flash._page_size >> 1):
                block = datablock[:(flash._page_size >> 1)]
                datablock = datablock[(flash._page_size >> 1):]
                if max(block) != 0:
                    self._stlink.set_mem32(data_addr, block)
                data_addr += len(block)
                self._dbg.bargraph_update(value=data_addr)
                flash.wait_busy(0.005, check_eop=True)
            self._stlink.set_debugreg32(flash._nvm + Flash.PECR_OFFSET, 0)
        flash.lock()
        self._dbg.bargraph_done()
        if verify:
            self._dbg.bargraph_start('Verify FLASH ', value_min=addr,
                                     value_max=addr + len(data))
            while(data):
                block = data[:64]
                data = data[64:]
                time.sleep(0.001) #FIXME: First read give wrong result w/o delay
                cblock = self._stlink.get_mem32(addr, len(block))
                #if block != cblock:
                    #raise lib.stlinkex.StlinkException (
                   #     'Verify error at block address: 0x%08x' % addr)
                addr += len(block)
                self._dbg.bargraph_update(value=addr)
            self._dbg.bargraph_done()
