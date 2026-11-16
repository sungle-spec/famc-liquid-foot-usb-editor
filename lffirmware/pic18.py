"""A small PIC18 disassembler — enough to *read* an LF+ firmware image, never to run or patch it.

The LF+ MCU is a PIC18 (128 KB class). Instructions are 16-bit little-endian words; ``GOTO``,
``CALL``, ``MOVFF`` and ``LFSR`` take a second word whose top nibble is ``1111``. This module
decodes the standard instruction set plus the extended (XINST) forms, and offers a recursive
traversal that separates reachable code from data so strings and tables can be found reliably.

Pure Python, no dependencies, no I/O. See docs/FIRMWARE_NOTES.md ("Inside the image").
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Flow kinds: how control leaves an instruction.
SEQ, JUMP, CJUMP, CALL, SKIP, RET, STOP = "seq", "jump", "cjump", "call", "skip", "ret", "stop"

_BYTE_OPS = {          # top 6 bits -> mnemonic (d, a, f operands)
    0b001001: "ADDWF", 0b001000: "ADDWFC", 0b000101: "ANDWF", 0b000111: "COMF",
    0b000001: "DECF", 0b001011: "DECFSZ", 0b010011: "DCFSNZ", 0b001010: "INCF",
    0b001111: "INCFSZ", 0b010010: "INFSNZ", 0b000100: "IORWF", 0b010100: "MOVF",
    0b001101: "RLCF", 0b010001: "RLNCF", 0b001100: "RRCF", 0b010000: "RRNCF",
    0b010101: "SUBFWB", 0b010111: "SUBWF", 0b010110: "SUBWFB", 0b001110: "SWAPF",
    0b000110: "XORWF",
}
_BYTE_OPS_A = {        # top 7 bits -> mnemonic (a, f operands; no destination bit)
    0b0110101: "CLRF", 0b0110001: "CPFSEQ", 0b0110010: "CPFSGT", 0b0110000: "CPFSLT",
    0b0110111: "MOVWF", 0b0000001: "MULWF", 0b0110110: "NEGF", 0b0110100: "SETF",
    0b0110011: "TSTFSZ",
}
_SKIPPERS = {"DECFSZ", "DCFSNZ", "INCFSZ", "INFSNZ", "CPFSEQ", "CPFSGT", "CPFSLT", "TSTFSZ",
             "BTFSC", "BTFSS"}
_BIT_OPS = {0b1001: "BCF", 0b1000: "BSF", 0b1011: "BTFSC", 0b1010: "BTFSS", 0b0111: "BTG"}
_COND_BRANCH = {0xE0: "BZ", 0xE1: "BNZ", 0xE2: "BC", 0xE3: "BNC", 0xE4: "BOV", 0xE5: "BNOV",
                0xE6: "BN", 0xE7: "BNN"}
_LITERAL_OPS = {0x0F: "ADDLW", 0x0B: "ANDLW", 0x09: "IORLW", 0x0E: "MOVLW", 0x0D: "MULLW",
                0x0C: "RETLW", 0x08: "SUBLW", 0x0A: "XORLW"}
_FIXED = {0x0000: "NOP", 0x0003: "SLEEP", 0x0004: "CLRWDT", 0x0005: "PUSH", 0x0006: "POP",
          0x0007: "DAW", 0x0014: "CALLW", 0x00FF: "RESET",
          0x0008: "TBLRD*", 0x0009: "TBLRD*+", 0x000A: "TBLRD*-", 0x000B: "TBLRD+*",
          0x000C: "TBLWT*", 0x000D: "TBLWT*+", 0x000E: "TBLWT*-", 0x000F: "TBLWT+*"}


@dataclass(frozen=True)
class Insn:
    addr: int               # byte address of the first word
    size: int               # 2 or 4 bytes
    mnemonic: str
    operands: str = ""
    flow: str = SEQ
    target: int | None = None    # branch/call destination (byte address)
    f: int | None = None         # file-register operand (12-bit data address where known)
    k: int | None = None         # literal operand
    bit: int | None = None
    access: bool = True          # True = access bank (a=0); False = BSR-banked (a=1)
    f2: int | None = None        # MOVFF destination

    @property
    def text(self) -> str:
        return f"{self.mnemonic} {self.operands}".strip()


def _signed(value: int, bits: int) -> int:
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def _file_addr(f: int, access: bool) -> int | None:
    """Absolute data address of an 8-bit file operand in the *access bank* (None when banked:
    the bank comes from BSR at run time). Access bank = 0x000-0x05F RAM + 0xF60-0xFFF SFRs."""
    if not access:
        return None
    return f if f < 0x60 else 0xF00 | f


def decode(mem: bytes, addr: int) -> Insn | None:
    """Decode the instruction at byte address ``addr`` (must be even). None if out of range."""
    if addr < 0 or addr + 1 >= len(mem) or addr & 1:
        return None
    w = mem[addr] | (mem[addr + 1] << 8)
    w2 = (mem[addr + 2] | (mem[addr + 3] << 8)) if addr + 3 < len(mem) else None
    hi, lo = w >> 8, w & 0xFF

    if w in _FIXED:
        name = _FIXED[w]
        return Insn(addr, 2, name, flow=STOP if name in ("RESET", "SLEEP") else SEQ)
    if w in (0x0010, 0x0011):
        return Insn(addr, 2, "RETFIE", "FAST" if w & 1 else "", flow=RET)
    if w in (0x0012, 0x0013):
        return Insn(addr, 2, "RETURN", "FAST" if w & 1 else "", flow=RET)
    if (w & 0xFFF0) == 0x0100:
        return Insn(addr, 2, "MOVLB", f"0x{w & 0xF:X}", k=w & 0xF)
    if hi in _LITERAL_OPS:
        name = _LITERAL_OPS[hi]
        return Insn(addr, 2, name, f"0x{lo:02X}", flow=RET if name == "RETLW" else SEQ, k=lo)

    top4 = w >> 12
    if top4 == 0xF:                       # stray second word — executes as NOP
        return Insn(addr, 2, "NOP", f"(0x{w:04X})")
    if top4 == 0xC:                       # MOVFF fs, fd
        if w2 is None or (w2 >> 12) != 0xF:
            return Insn(addr, 2, "?MOVFF", f"0x{w:04X}", flow=STOP)
        src, dst = w & 0xFFF, w2 & 0xFFF
        return Insn(addr, 4, "MOVFF", f"0x{src:03X}, 0x{dst:03X}", f=src, f2=dst)
    if top4 == 0xD:                       # BRA / RCALL
        target = (addr + 2 + 2 * _signed(w & 0x7FF, 11)) & 0x1FFFFF
        if w & 0x0800:
            return Insn(addr, 2, "RCALL", f"0x{target:05X}", flow=CALL, target=target)
        return Insn(addr, 2, "BRA", f"0x{target:05X}", flow=JUMP, target=target)
    if hi in _COND_BRANCH:
        target = (addr + 2 + 2 * _signed(lo, 8)) & 0x1FFFFF
        return Insn(addr, 2, _COND_BRANCH[hi], f"0x{target:05X}", flow=CJUMP, target=target)
    if hi in (0xEC, 0xED, 0xEF):          # CALL / GOTO (two words)
        if w2 is None or (w2 >> 12) != 0xF:
            return Insn(addr, 2, "?CALL/GOTO", f"0x{w:04X}", flow=STOP)
        target = ((w2 & 0xFFF) << 8 | lo) << 1
        if hi == 0xEF:
            return Insn(addr, 4, "GOTO", f"0x{target:05X}", flow=JUMP, target=target)
        return Insn(addr, 4, "CALL", f"0x{target:05X}" + (", FAST" if hi & 1 else ""),
                    flow=CALL, target=target)
    if hi == 0xEE and (lo & 0xC0) == 0:   # LFSR f, k (two words)
        if w2 is None or (w2 & 0xFF00) != 0xF000:
            return Insn(addr, 2, "?LFSR", f"0x{w:04X}", flow=STOP)
        k = ((lo & 0x0F) << 8) | (w2 & 0xFF)
        return Insn(addr, 4, "LFSR", f"{(lo >> 4) & 3}, 0x{k:03X}", k=k, bit=(lo >> 4) & 3)
    if hi == 0xE8:                        # ADDFSR / ADDULNK (extended)
        fsr, k = lo >> 6, lo & 0x3F
        return Insn(addr, 2, "ADDULNK" if fsr == 3 else "ADDFSR",
                    f"0x{k:02X}" if fsr == 3 else f"{fsr}, 0x{k:02X}",
                    flow=RET if fsr == 3 else SEQ, k=k)
    if hi == 0xE9:                        # SUBFSR / SUBULNK (extended)
        fsr, k = lo >> 6, lo & 0x3F
        return Insn(addr, 2, "SUBULNK" if fsr == 3 else "SUBFSR",
                    f"0x{k:02X}" if fsr == 3 else f"{fsr}, 0x{k:02X}",
                    flow=RET if fsr == 3 else SEQ, k=k)
    if hi == 0xEA:                        # PUSHL (extended)
        return Insn(addr, 2, "PUSHL", f"0x{lo:02X}", k=lo)
    if hi == 0xEB:                        # MOVSF / MOVSS (extended, two words)
        if w2 is None or (w2 >> 12) != 0xF:
            return Insn(addr, 2, "?MOVS", f"0x{w:04X}", flow=STOP)
        if lo & 0x80:
            return Insn(addr, 4, "MOVSS", f"[0x{lo & 0x7F:02X}], [0x{w2 & 0x7F:02X}]")
        return Insn(addr, 4, "MOVSF", f"[0x{lo & 0x7F:02X}], 0x{w2 & 0xFFF:03X}", f2=w2 & 0xFFF)

    if top4 in _BIT_OPS:
        name = _BIT_OPS[top4]
        bit, access = (w >> 9) & 7, not (w & 0x0100)
        return Insn(addr, 2, name, f"0x{lo:02X}, {bit}" + ("" if access else ", BANKED"),
                    flow=SKIP if name in _SKIPPERS else SEQ, f=_file_addr(lo, access), bit=bit,
                    access=access)
    top7 = w >> 9
    if top7 in _BYTE_OPS_A:
        name, access = _BYTE_OPS_A[top7], not (w & 0x0100)
        return Insn(addr, 2, name, f"0x{lo:02X}" + ("" if access else ", BANKED"),
                    flow=SKIP if name in _SKIPPERS else SEQ, f=_file_addr(lo, access),
                    access=access)
    top6 = w >> 10
    if top6 in _BYTE_OPS:
        name, access, dest_f = _BYTE_OPS[top6], not (w & 0x0100), bool(w & 0x0200)
        return Insn(addr, 2, name, f"0x{lo:02X}, {'F' if dest_f else 'W'}"
                    + ("" if access else ", BANKED"),
                    flow=SKIP if name in _SKIPPERS else SEQ, f=_file_addr(lo, access),
                    access=access, k=1 if dest_f else 0)
    return Insn(addr, 2, "?", f"0x{w:04X}", flow=STOP)


@dataclass
class CodeMap:
    """Result of a recursive traversal: which bytes are reachable code, and the call structure."""
    insns: dict[int, Insn] = field(default_factory=dict)       # addr -> instruction
    functions: set[int] = field(default_factory=set)            # CALL/RCALL targets + entry points
    calls: dict[int, set[int]] = field(default_factory=dict)    # callee -> {call-site addrs}
    jumps: dict[int, set[int]] = field(default_factory=dict)    # jump target -> {source addrs}
    out_of_image: dict[int, set[int]] = field(default_factory=dict)  # target >= len -> sources
    bad: set[int] = field(default_factory=set)                  # addresses that failed to decode

    def code_bytes(self) -> int:
        return sum(i.size for i in self.insns.values())

    def is_code(self, addr: int) -> bool:
        return addr in self.insns

    def covered(self, size: int) -> bytearray:
        cov = bytearray(size)
        for a, i in self.insns.items():
            for b in range(a, min(size, a + i.size)):
                cov[b] = 1
        return cov


def trace(mem: bytes, entries) -> CodeMap:
    """Follow control flow from ``entries`` (byte addresses). Conservative: computed jumps
    (writes to PCL, CALLW) are not followed, so jump-table targets may be missed."""
    cm = CodeMap()
    work = list(entries)
    cm.functions.update(e for e in entries if 0 <= e < len(mem))
    size = len(mem)
    while work:
        addr = work.pop()
        while 0 <= addr < size and addr not in cm.insns:
            ins = decode(mem, addr)
            if ins is None or ins.mnemonic.startswith("?"):
                cm.bad.add(addr)
                break
            cm.insns[addr] = ins
            nxt = addr + ins.size
            if ins.target is not None:
                if ins.target >= size:
                    cm.out_of_image.setdefault(ins.target, set()).add(addr)
                elif ins.flow == CALL:
                    cm.calls.setdefault(ins.target, set()).add(addr)
                    cm.functions.add(ins.target)
                    work.append(ins.target)
                else:
                    cm.jumps.setdefault(ins.target, set()).add(addr)
                    work.append(ins.target)
            if ins.flow == SKIP:
                # the skipped instruction may be 2 words: both successors are possible
                skipped = decode(mem, nxt)
                if skipped is not None:
                    work.append(nxt + skipped.size)
            if ins.flow in (JUMP, RET, STOP):
                break
            addr = nxt
    return cm


def linear(mem: bytes, start: int, end: int):
    """Plain linear sweep over [start, end) — for listing a known code range."""
    addr = start & ~1
    while addr < end:
        ins = decode(mem, addr)
        if ins is None:
            return
        yield ins
        addr += ins.size
