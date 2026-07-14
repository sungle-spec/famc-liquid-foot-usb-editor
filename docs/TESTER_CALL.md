# Forum post draft — firmware loader tester call

Copy-paste below the line (plain text, Facebook-safe).

---

**Bricked your Liquid Foot+ with a firmware update? We might be able to bring it back — testers wanted**

Since launching the editor, the most common question has been firmware loading — usually from people whose unit died during a firmware update with the original editor. I've built a standalone **LF+ Firmware Loader** to tackle exactly that, and I need testers before it's ready for general use.

**The good news, from digging into how these units actually work:**

• The LF+ has a built-in rescue mode that doesn't need working firmware: hold **B7 while powering on** and the unit waits to receive firmware over its MIDI IN socket (it's in the official manual, p.15). That means many "bricked" units are likely recoverable.

• The loader sends firmware exactly the way FAMC's own editor did — plus checks FAMC never had: it verifies your firmware file against a database of **241 known-genuine FAMC releases** (v3.34–v6.32, all five models) and physically refuses to send wrong-model or corrupted files, which I suspect caused some of these bricks in the first place.

**Who I'm looking for, in order:**

1. **Anyone with a BRICKED unit** (any model — 12+, 12, Mini, JR+, Pro+). Your unit can't get more dead — you're the safest possible test, and you might get it back. You'll need a basic USB-MIDI interface and the firmware file for your model (from your old editor install — I can help you locate/verify it).

2. **One person with a WORKING unit + the original FAMC editor on a Mac**, willing to run a normal firmware update once while a small logging tool records what goes over the cable. Zero changes to your process — it just watches. This confirms the last protocol detail before anyone flashes anything with the new tool.

3. Later: a working-unit owner willing to re-flash their current version with the new loader (the lowest-risk real test — full backup first, of course).

**Ground rules:** bricked units first, full logs from every attempt, nothing gets flashed on a working unit until the recovery path has proven itself. Everything is at your own risk — a failed flash may be beyond software recovery — but the worst case for an already-bricked unit is that it stays bricked, and every attempt teaches us something.

Comment or DM if you're in, with your model and what state it's in. The technical write-up is here if you want the details: https://github.com/sungle-spec/famc-liquid-foot-usb-editor/blob/main/docs/FIRMWARE_LOADER.md
