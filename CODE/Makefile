#	*************************************************************************
#	* S6ED MSX2 Screen 6 Text Editor					 	                *
#	* (c) 2024 - 2025 Armando Pérez            						    	*
#	*************************************************************************

.PHONY: build build-s6 build-s2 build-s62 dsk dsk-s2 dsk-s62 s6 s2 s62 clean check gate test \
        test-s2 selftest testall \
        run run-s6 run128 run-s6-128 run-nextor debug \
        run-s2 run-s2-1mb run-s2-msx2 run-s2-msx2-128 \
        run-s62 run-s62-128

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
DSKFAT			= python3 ../../msxtools/scripts/dskfat.py
DSKBASE			= $(RES_DIR)/DOS2.DSK

# --- S2 (Screen 2 TMS9918) Targets -------------------------------------
SOURCE_S2		= S2ED.Z8A
CFGFILE_S2		= S2ED.CFG
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

# --- S62 (Screen 6 62-col 8x8 font) Targets -----------------------------
SOURCE_S62		= S62ED.Z8A
CFGFILE_S62		= S62ED.CFG
OUTPUT_S62		= S62ED.COM
FNTFILE_S62		= S62ED.FNT
DATFILE_S62		= S62ED.DAT
DSKFILE_S62		= S62ED.DSK
LSTFILE_S62		= S62ED.lst
SYMFILE_S62		= S62ED.sym

INCLUDES_S62 		= -I.	\
			  -I$(RES_DIR) \
			  -I$(SRC_DIR) \
			  -I$(SRC_DIR)/CORE \
			  -I$(SRC_DIR)/S62 \

# -	 All Target --------------------------------------------------------------

all: build dsk

# -	 Clean Target ------------------------------------------------------------

clean:
	@$(RM) -R $(OUTPUT) $(DATFILE) $(LSTFILE) $(SYMFILE) $(DSKFILE) $(FNTFILE) \
		$(OUTPUT_S2) $(DATFILE_S2) $(LSTFILE_S2) $(SYMFILE_S2) $(DSKFILE_S2) $(FNTFILE_S2) \
		$(OUTPUT_S62) $(DATFILE_S62) $(LSTFILE_S62) $(SYMFILE_S62) $(DSKFILE_S62) $(FNTFILE_S62) \
		$(MANUAL)

# `build` means the PROJECT, every target.  It used to mean S6ED alone while
# `clean` removed the artefacts of both, so `make clean build` left the tree
# half built -- and the S2 half of the harness then died on a .sym that did
# not exist.  The per-target names stay available, and the runners use them so
# that running one editor still assembles only that one.
build: build-s6 build-s2 build-s62

build-s6: $(OUTPUT) $(DATFILE) $(FNTFILE)

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

# The disks are laid out the way the editors are meant to be installed: the
# programs with their DAT, FNT and general CFG in A:\TOOLS, which
# AUTOEXEC.BAT puts on the PATH, and the documents in A:\DEV, which is where
# the editor is run from -- together with a local CFG that is read after the
# general one.  Testing from the root hid that DAT, FNT and CFG were opened in
# the current directory; this layout keeps it from hiding anything again.
# dsktool knows only the root, so the directories are written by dskfat.
#
# The S6ED disk carries S2ED and S62ED too.  An MSX2 runs all three editors,
# so one image lets them be compared side by side without swapping disks:
# boot goes to S6ED through AUTOEXEC.BAT, and `S2ED TEST_S2.TXT` or
# `S62ED TEST_S62.TXT` starts the others.
#
# The manual is kept in UTF-8 in DOC/ so it reads and diffs on the host, and
# converted to the MSX charset with CR LF on the way to the disks: shipped as
# UTF-8 every accented letter showed as two glyphs.  utf8msx refuses any
# character the MSX charset has no code for, so the build fails instead.
MANUALSRC		= ../DOC/SXED.TXT
MANUAL			= SXED_MSX.TXT
UTF8MSX			= python3 ../../msxtools/scripts/utf8msx.py

$(MANUAL): $(MANUALSRC)
	@$(UTF8MSX) $< $@

DSKTOOLS		= $(OUTPUT) $(DATFILE) $(FNTFILE) S6ED.CFG \
			  $(OUTPUT_S2) $(DATFILE_S2) $(FNTFILE_S2) $(CFGFILE_S2) \
			  $(OUTPUT_S62) $(DATFILE_S62) $(FNTFILE_S62) $(CFGFILE_S62)
DSKCONT			= $(DSKTOOLS) $(MANUAL) TEST.TXT TEST_S2.TXT TEST_S62.TXT \
			  LOCAL_S6.CFG LOCAL_S2.CFG LOCAL_S62.CFG AUTOEXEC.BAT

$(DSKFILE): $(DSKCONT)
	@cp $(DSKBASE) $(DSKFILE)
	@$(DSKFAT) $(DSKFILE) add . AUTOEXEC.BAT
	@$(DSKFAT) $(DSKFILE) add TOOLS $(DSKTOOLS)
	@$(DSKFAT) $(DSKFILE) add DEV $(MANUAL)=SXED.TXT TEST.TXT TEST_S2.TXT TEST_S62.TXT \
		LOCAL_S6.CFG=S6ED.CFG LOCAL_S2.CFG=S2ED.CFG LOCAL_S62.CFG=S62ED.CFG

# -	 S2 Targets --------------------------------------------------------------

s2: run-s2

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

DSKCONT_S2		= $(OUTPUT_S2) $(DATFILE_S2) $(FNTFILE_S2) $(CFGFILE_S2)

# Same layout as the S6ED disk.  The S2 sample document talks about 64 columns
# and Screen 2, so it goes in as \DEV\TEST.TXT, and the S2 AUTOEXEC as the
# root AUTOEXEC.BAT: dskfat takes the on-disk name after the '='.
$(DSKFILE_S2): $(DSKCONT_S2) $(MANUAL) TEST_S2.TXT AUTOEXEC_S2.BAT LOCAL_S2.CFG
	@cp $(DSKBASE) $(DSKFILE_S2)
	@$(DSKFAT) $(DSKFILE_S2) add . AUTOEXEC_S2.BAT=AUTOEXEC.BAT
	@$(DSKFAT) $(DSKFILE_S2) add TOOLS $(DSKCONT_S2)
	@$(DSKFAT) $(DSKFILE_S2) add DEV $(MANUAL)=SXED.TXT TEST_S2.TXT=TEST.TXT LOCAL_S2.CFG=S2ED.CFG

# -	 S62 Targets -------------------------------------------------------------

s62: run-s62

build-s62: $(OUTPUT_S62) $(DATFILE_S62) $(FNTFILE_S62)

$(DATFILE_S62): $(OUTPUT_S62)
	@if [ ! -f $(DATFILE_S62) ]; then \
		$(ASM) --lst=$(LSTFILE_S62) --sym=$(SYMFILE_S62) $(INCLUDES_S62) $(DEFINES) $(SRC_DIR)/$(SOURCE_S62); \
	fi

$(OUTPUT_S62): $(ALL_SOURCES_GEN)
	@$(ASM) --lst=$(LSTFILE_S62) --sym=$(SYMFILE_S62) $(INCLUDES_S62) $(DEFINES) $(SRC_DIR)/$(SOURCE_S62)

$(FNTFILE_S62): $(RES_DIR)/FONTS_S62.BIN
	@cp $< $@

$(RES_DIR)/FONTS_S62.BIN: $(RES_DIR)/FONT_BIOS8X8.BIN
	cat $< $< $< $< > $@

dsk-s62: $(DSKFILE_S62)

DSKCONT_S62		= $(OUTPUT_S62) $(DATFILE_S62) $(FNTFILE_S62) $(CFGFILE_S62)

$(DSKFILE_S62): $(DSKCONT_S62) $(MANUAL) TEST_S62.TXT AUTOEXEC_S62.BAT LOCAL_S62.CFG
	@cp $(DSKBASE) $(DSKFILE_S62)
	@$(DSKFAT) $(DSKFILE_S62) add . AUTOEXEC_S62.BAT=AUTOEXEC.BAT
	@$(DSKFAT) $(DSKFILE_S62) add TOOLS $(DSKCONT_S62)
	@$(DSKFAT) $(DSKFILE_S62) add DEV $(MANUAL)=SXED.TXT TEST_S62.TXT=TEST.TXT LOCAL_S62.CFG=S62ED.CFG

run-s62-128: build-s62 dsk-s62
	m2d2 128k $(DSKFILE_S62)

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
 
s6: run-s6

run: run-s6

run-s6: build dsk
	m2d2 $(DSKFILE)

# Minimum-spec check: stock 128 kB Philips NMS 8250
run128: run-s6-128

run-s6-128: build dsk
	m2d2 128k $(DSKFILE)

run-s62: build-s62 dsk-s62
	m2d2 $(DSKFILE_S62)

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
