#	*************************************************************************
#	* S6ED MSX2 Screen 6 Text Editor					 	                *
#	* (c) 2024 - 2025 Armando Pérez            						    	*
#	*************************************************************************

.PHONY: build run clean check gate test test-s2 selftest testall \
        run-s2 run-s2-1mb run-s2-msx2 run-s2-msx2-128

# 	=========================================================================
# 	CONSTANTS
# 	=========================================================================

SOURCE			= S6ED.Z8A
OUTPUT			= S6ED.COM
ASM				= sjasmplus
SYMFILE			= $(basename $(SOURCE)).sym
LSTFILE			= $(basename $(SOURCE)).lst
SRC_DIR			= SRC
RES_DIR			= ../RES

# 	=========================================================================
# 	VARS
# 	=========================================================================

MAIN 			= $(SRC_DIR)/$(SOURCE)
ALL_SOURCES_GEN	= $(shell find $(SRC_DIR) -type f -name "*.Z8A" ! -wholename "*.svn*" ! -wholename "*.DS_Store*" ! -regex "\./\..*" ! -regex "\.")

#	=========================================================================
# 	Includes & Defines
#	=========================================================================

INCLUDES 		= -I.	\
			  -I$(RES_DIR) \
			  -I$(SRC_DIR) \
			  -I$(SRC_DIR)/CORE \
			  -I$(SRC_DIR)/S6 \

DEFINES			= -DON=1 -DOFF=0

# DEBUG=1 enables the DBG macro (openMSX debugdevice, ports #2E/#2F).
# Without it the macro and DBGMSG assemble to nothing.
ifeq ($(DEBUG),1)
DEFINES			+= -DDEBUG
endif

# The font is no longer built into the image. FONTINIT reads S6ED.FNT from the
# disk at startup and falls back to the MSX ROM charset when it is missing, so
# there is one binary and no FONTBIN switch: the choice is made at run time by
# whether the file is there.
FNTFILE			= S6ED.FNT
DATFILE			= S6ED.DAT

DSKFILE			= S6ED.DSK
DSKTOOL			= ../../msxtools/bin/dsktool
DSKBASE			= $(RES_DIR)/DOS2.DSK

# --- S2 (Screen 2 TMS9918) Targets -------------------------------------
SOURCE_S2		= S2ED.Z8A
OUTPUT_S2		= S2ED.COM
FNTFILE_S2		= S2ED.FNT
DATFILE_S2		= S2ED.DAT
DSKFILE_S2		= S2ED.DSK
LSTFILE_S2		= S2ED.lst
SYMFILE_S2		= S2ED.sym

INCLUDES_S2 		= -I.	\
			  -I$(RES_DIR) \
			  -I$(SRC_DIR) \
			  -I$(SRC_DIR)/CORE \
			  -I$(SRC_DIR)/S2 \

# -	 All Target --------------------------------------------------------------

all: build dsk

# -	 Clean Target ------------------------------------------------------------

clean:
	@$(RM) -R $(OUTPUT) $(DATFILE) $(LSTFILE) $(SYMFILE) $(DSKFILE) $(FNTFILE) \
		$(OUTPUT_S2) $(DATFILE_S2) $(LSTFILE_S2) $(SYMFILE_S2) $(DSKFILE_S2) $(FNTFILE_S2)

build: $(OUTPUT) $(DATFILE) $(FNTFILE)

# S6ED.DAT is written by the same sjasmplus run as S6ED.COM (rotating OUTPUT
# directive in S6ED.Z8A), so normally it simply follows the .COM. The recipe
# covers the case where the .DAT is deleted while the .COM is still up to
# date: without it make considered the missing .DAT "updated" and the disk
# image went out with a stale or absent container.
$(DATFILE): $(OUTPUT)
	@if [ ! -f $(DATFILE) ]; then \
		$(ASM) --lst=$(LSTFILE) --sym=$(SYMFILE) $(INCLUDES) $(DEFINES) $(MAIN); \
	fi

dsk: $(DSKFILE)

DSKCONT			= $(OUTPUT) $(DATFILE) $(FNTFILE) TEST.TXT AUTOEXEC.BAT S6ED.CFG

$(DSKFILE): $(DSKCONT)
	@cp $(DSKBASE) $(DSKFILE)
	@$(DSKTOOL) D $(DSKFILE) $(DSKCONT)
	@$(DSKTOOL) A $(DSKFILE) $(DSKCONT)

# -	 S2 Targets --------------------------------------------------------------

s2: build-s2 dsk-s2

build-s2: $(OUTPUT_S2) $(DATFILE_S2) $(FNTFILE_S2)

$(DATFILE_S2): $(OUTPUT_S2)
	@if [ ! -f $(DATFILE_S2) ]; then \
		$(ASM) --lst=$(LSTFILE_S2) --sym=$(SYMFILE_S2) $(INCLUDES_S2) $(DEFINES) $(SRC_DIR)/$(SOURCE_S2); \
	fi

$(OUTPUT_S2): $(ALL_SOURCES_GEN)
	@$(ASM) --lst=$(LSTFILE_S2) --sym=$(SYMFILE_S2) $(INCLUDES_S2) $(DEFINES) $(SRC_DIR)/$(SOURCE_S2)

$(FNTFILE_S2): $(RES_DIR)/FONTS_S2.BIN
	@cp $< $@

$(RES_DIR)/FONTS_S2.BIN: $(RES_DIR)/FONT4X8.PNG $(RES_DIR)/fontcheck_s2.py
	python3 $(RES_DIR)/fontcheck_s2.py $< --out $@

dsk-s2: $(DSKFILE_S2)

CFGFILE_S2		= S2ED.CFG
DSKCONT_S2		= $(OUTPUT_S2) $(DATFILE_S2) $(FNTFILE_S2) $(CFGFILE_S2)

# TEST.TXT and AUTOEXEC.BAT ship under names the S6ED disk uses too, and
# dsktool takes the on-disk name from the host file, so the S2 variants are
# swapped in around the add and put straight back.  The sample document is a
# different one: it talks about 64 columns and Screen 2.
$(DSKFILE_S2): $(DSKCONT_S2) TEST_S2.TXT AUTOEXEC_S2.BAT
	@cp $(DSKBASE) $(DSKFILE_S2)
	@$(DSKTOOL) D $(DSKFILE_S2) $(DSKCONT_S2) TEST.TXT AUTOEXEC.BAT
	@$(DSKTOOL) A $(DSKFILE_S2) $(DSKCONT_S2)
	@cp TEST.TXT TEST.S6.TMP
	@cp AUTOEXEC.BAT AUTOEXEC.S6.TMP
	@cp TEST_S2.TXT TEST.TXT
	@cp AUTOEXEC_S2.BAT AUTOEXEC.BAT
	@$(DSKTOOL) A $(DSKFILE_S2) TEST.TXT AUTOEXEC.BAT
	@mv TEST.S6.TMP TEST.TXT
	@mv AUTOEXEC.S6.TMP AUTOEXEC.BAT

# -	 Build Target ------------------------------------------------------------

# The asset ships next to the .COM under its run-time name, so anyone with the
# format can drop in their own face.
$(FNTFILE): $(RES_DIR)/FONTS.BIN
	@cp $< $@

$(RES_DIR)/FONTS.BIN: $(RES_DIR)/FONT.PNG $(RES_DIR)/fontcheck.py
	python3 $(RES_DIR)/fontcheck.py $< --variant normal --out $(RES_DIR)/FONT_NORM.BIN
	python3 $(RES_DIR)/fontcheck.py $< --variant bold --out $(RES_DIR)/FONT_BOLD.BIN
	python3 $(RES_DIR)/fontcheck.py $< --variant italic --out $(RES_DIR)/FONT_ITAL.BIN
	python3 $(RES_DIR)/fontcheck.py $< --variant bolditalic --out $(RES_DIR)/FONT_BI.BIN
	cat $(RES_DIR)/FONT_NORM.BIN $(RES_DIR)/FONT_BOLD.BIN $(RES_DIR)/FONT_ITAL.BIN $(RES_DIR)/FONT_BI.BIN > $@
	@$(RM) $(RES_DIR)/FONT_NORM.BIN $(RES_DIR)/FONT_BOLD.BIN $(RES_DIR)/FONT_ITAL.BIN $(RES_DIR)/FONT_BI.BIN

$(OUTPUT): $(ALL_SOURCES_GEN)
	@$(ASM) --lst=$(LSTFILE) --sym=$(SYMFILE) $(INCLUDES) $(DEFINES) $(MAIN)

# -	 Run Targets -------------------------------------------------------------

run: build dsk
	m2d2 $(DSKFILE)

# Minimum-spec check: stock 128 kB Philips NMS 8250
run128: build dsk
	m2d2 128k $(DSKFILE)

# S2ED's target is an MSX1, so that is what `run-s2` gives you.  MSX-DOS 2
# does not run on an MSX1 (the kernel halts at #4005), so m1d2 boots a Nextor
# kernel on a Sony HB-20P with slot 3 expanded into a 128 kB mapper plus a disk
# interface: a real TMS9918-class VDP, and SEGTOT 8 / SEGAVL 0 -- the same
# segment budget as a stock NMS 8250.
run-s2: build-s2 dsk-s2
	m1d2 $(DSKFILE_S2)

# Same machine with a 1 MB mapper: for debugging WITHOUT the segment ceiling,
# never for concluding that something fits.
run-s2-1mb: build-s2 dsk-s2
	m1d2 1mb $(DSKFILE_S2)

# The MSX2 machines run S2ED too (it is a DOS program, and Screen 2 exists on a
# V9938).  Useful only to compare the S2 driver against the S6 one on identical
# hardware -- the VDP is wrong and the mapper is roomy, so neither is the
# machine to judge S2ED on.
run-s2-msx2: build-s2 dsk-s2
	m2d2 $(DSKFILE_S2)

run-s2-msx2-128: build-s2 dsk-s2
	m2d2 128k $(DSKFILE_S2)

# Nextor 2.1 check: Nextor standalone kernel on 2 MB
run-nextor: build dsk
	m2d2 nextor $(DSKFILE)

# Debug build, with the DBG trace captured from the openMSX debug device
debug:
	@$(MAKE) DEBUG=1 build dsk
	m2d2 $(DSKFILE) -ext debugdevice

log:
	@echo $(ALL_SOURCES_GEN)

# -	 Test Targets ------------------------------------------------------------
#
# check    T0 only: static invariants, no emulator (~0.2 s)
# gate     the runtime Gate: the headless openMSX sessions (~30 s)
# test     both -- run this before calling an integration finished
# selftest reintroduces each historical defect and proves the Gate goes red
# testall  every one of the three, in one run, printing every check (~1 min).
#          Nothing short-circuits: a failure in one section does not stop the
#          next, so one command shows the whole picture.

TESTDIR			= ../TEST

check:
	@$(TESTDIR)/runtests.py --static

gate:
	@$(TESTDIR)/runtests.py --gate

# Suite S2: the MSX1 / SCREEN 2 gate, on Custom_MSX1_DOS2 under Nextor.
test-s2:
	@$(TESTDIR)/runtests.py --s2

test:
	@$(TESTDIR)/runtests.py

selftest:
	@$(TESTDIR)/runtests.py --selftest

testall:
	@$(TESTDIR)/runtests.py --all
