import os
import sys
import subprocess

from migen.build.generic_programmer import GenericProgrammer


def _run_urjtag(cmds):
    with subprocess.Popen("jtag", stdin=subprocess.PIPE) as process:
        process.stdin.write(cmds.encode("ASCII"))
        process.communicate()


class UrJTAG(GenericProgrammer):
    needs_bitreverse = True

    def __init__(self, cable, flash_proxy_basename=None):
        GenericProgrammer.__init__(self, flash_proxy_basename)
        self.cable = cable

    def load_bitstream(self, bitstream_file):
        cmds = """cable {cable}
detect
pld load {bitstream}
quit
""".format(bitstream=bitstream_file, cable=self.cable)
        _run_urjtag(cmds)

    def flash(self, address, data_file):
        flash_proxy = self.find_flash_proxy()
        cmds = """cable {cable}
detect
pld load "{flash_proxy}"
initbus fjmem opcode=000010
frequency 6000000
detectflash 0
endian big
flashmem "{address}" "{data_file}" noverify
""".format(flash_proxy=flash_proxy, address=address, data_file=data_file,
           cable=self.cable)
        _run_urjtag(cmds)


class XC3SProg(GenericProgrammer):
    needs_bitreverse = False

    def __init__(self, cable, flash_proxy_basename=None):
        GenericProgrammer.__init__(self, flash_proxy_basename)
        self.cable = cable

    def load_bitstream(self, bitstream_file):
        subprocess.call(["xc3sprog", "-v", "-c", self.cable, bitstream_file])

    def flash(self, address, data_file):
        flash_proxy = self.find_flash_proxy()
        subprocess.call(["xc3sprog", "-v", "-c", self.cable, "-I"+flash_proxy, "{}:w:0x{:x}:BIN".format(data_file, address)])



class FpgaProg(GenericProgrammer):
    needs_bitreverse = False

    def __init__(self, flash_proxy_basename=None):
        GenericProgrammer.__init__(self, flash_proxy_basename)

    def load_bitstream(self, bitstream_file):
        subprocess.call(["fpgaprog", "-v", "-f", bitstream_file])

    def flash(self, address, data_file):
        if address != 0:
            raise ValueError("fpga prog needs a main bitstream at address 0")
        flash_proxy = self.find_flash_proxy()
        subprocess.call(["fpgaprog", "-v", "-sa", "-r", "-b", flash_proxy,
                   "-f", data_file])


def _run_impact(cmds):
    with subprocess.Popen("impact -batch", stdin=subprocess.PIPE, shell=True) as process:
        process.stdin.write(cmds.encode("ASCII"))
        process.communicate()
        return process.returncode


def _create_xsvf(bitstream_file, xsvf_file):
    assert os.path.exists(bitstream_file), bitstream_file
    assert not os.path.exists(xsvf_file), xsvf_file
    assert 0 == _run_impact("""
setPreference -pref KeepSVF:True
setMode -bs
setCable -port xsvf -file {xsvf}
addDevice -p 1 -file {bitstream}
program -p 1
quit
""".format(bitstream=bitstream_file, xsvf=xsvf_file))


class iMPACT(GenericProgrammer):
    needs_bitreverse = False

    def load_bitstream(self, bitstream_file):
        cmds = """setMode -bs
setCable -p auto
addDevice -p 1 -file {bitstream}
program -p 1
quit
""".format(bitstream=bitstream_file)
        _run_impact(cmds)


def _run_vivado(cmds):
    with subprocess.Popen("vivado -mode tcl", stdin=subprocess.PIPE, shell=True) as process:
        process.stdin.write(cmds.encode("ASCII"))
        process.communicate()


class VivadoProgrammer(GenericProgrammer):
    needs_bitreverse = False
    def __init__(self, flash_part="n25q256-3.3v-spi-x1_x2_x4"):
        GenericProgrammer.__init__(self)
        self.flash_part = flash_part

    def load_bitstream(self, bitstream_file, target="", device=0):
        cmds = """open_hw
connect_hw_server
open_hw_target {target}

set_property PROBES.FILE {{}} [lindex [get_hw_devices] {{{device}}}]
set_property PROGRAM.FILE {{{bitstream}}} [lindex [get_hw_devices] {{{device}}}]

program_hw_devices [lindex [get_hw_devices] {{{device}}}]
refresh_hw_device [lindex [get_hw_devices] {{{device}}}]

quit
""".format(target=target, bitstream=bitstream_file, device=device)
        _run_vivado(cmds)

    # XXX works to flash bitstream, adapt it to flash bios
    def flash(self, address, data_file, device=0):
        cmds = """open_hw
connect_hw_server
open_hw_target
create_hw_cfgmem -hw_device [lindex [get_hw_devices] {{{device}}}] -mem_dev  [lindex [get_cfgmem_parts {{{flash_part}}}] 0]

set_property PROGRAM.BLANK_CHECK  0 [ get_property PROGRAM.HW_CFGMEM [lindex [get_hw_devices] {{{device}}} ]]
set_property PROGRAM.ERASE  1 [ get_property PROGRAM.HW_CFGMEM [lindex [get_hw_devices] {{{device}}} ]]
set_property PROGRAM.CFG_PROGRAM  1 [ get_property PROGRAM.HW_CFGMEM [lindex [get_hw_devices] {{{device}}} ]]
set_property PROGRAM.VERIFY  1 [ get_property PROGRAM.HW_CFGMEM [lindex [get_hw_devices] {{{device}}} ]]
refresh_hw_device [lindex [get_hw_devices] {{{device}}}]

set_property PROGRAM.ADDRESS_RANGE  {{use_file}} [ get_property PROGRAM.HW_CFGMEM [lindex [get_hw_devices] {{{device}}} ]]
set_property PROGRAM.FILES [list "{data}" ] [ get_property PROGRAM.HW_CFGMEM [lindex [get_hw_devices] {{{device}}}]]
set_property PROGRAM.UNUSED_PIN_TERMINATION {{pull-none}} [ get_property PROGRAM.HW_CFGMEM [lindex [get_hw_devices] {{{device}}} ]]
set_property PROGRAM.BLANK_CHECK  0 [ get_property PROGRAM.HW_CFGMEM [lindex [get_hw_devices] {{{device}}} ]]
set_property PROGRAM.ERASE  1 [ get_property PROGRAM.HW_CFGMEM [lindex [get_hw_devices] {{{device}}} ]]
set_property PROGRAM.CFG_PROGRAM  1 [ get_property PROGRAM.HW_CFGMEM [lindex [get_hw_devices] {{{device}}} ]]
set_property PROGRAM.VERIFY  1 [ get_property PROGRAM.HW_CFGMEM [lindex [get_hw_devices] {{{device}}} ]]

startgroup
if {{![string equal [get_property PROGRAM.HW_CFGMEM_TYPE  [lindex [get_hw_devices] {{{device}}}]] [get_property MEM_TYPE [get_property CFGMEM_PART [get_property PROGRAM.HW_CFGMEM [lindex [get_hw_devices] {{{device}}} ]]]]] }}  {{ create_hw_bitstream -hw_device [lindex [get_hw_devices] {{{device}}}] [get_property PROGRAM.HW_CFGMEM_BITFILE [ lindex [get_hw_devices] {{{device}}}]]; program_hw_devices [lindex [get_hw_devices] {{{device}}}]; }};
program_hw_cfgmem -hw_cfgmem [get_property PROGRAM.HW_CFGMEM [lindex [get_hw_devices] {{{device}}} ]]
endgroup

quit
""".format(data=data_file, flash_part=self.flash_part, device=device)
        _run_vivado(cmds)


class Adept(GenericProgrammer):
    """Using the Adept tool with an onboard Digilent "USB JTAG" cable.

    You need to install Adept Utilities V2 from
    http://www.digilentinc.com/Products/Detail.cfm?NavPath=2,66,828&Prod=ADEPT2
    """

    needs_bitreverse = False

    def __init__(self, board, index, flash_proxy_basename=None):
        GenericProgrammer.__init__(self, flash_proxy_basename)
        self.board = board
        self.index = index

    def load_bitstream(self, bitstream_file):
        subprocess.call([
            "djtgcfg",
            "--verbose",
            "prog", "-d", self.board,
            "-i", str(self.index),
            "-f", bitstream_file,
            ])

    def flash(self, address, data_file):
        raise ValueError("Flashing unsupported with DigilentAdept tools")
