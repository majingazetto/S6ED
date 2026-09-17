#	*************************************************************************
#	* S6ED MSX2 Screen 6 Text Editor					 	                *
#	* (c) 2024 - 2025 Armando Pérez            						    	*
#	*************************************************************************

.PHONY: build run clean check gate test selftest testall

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

# -	 All Target --------------------------------------------------------------

all: build dsk

# -	 Clean Target ------------------------------------------------------------

clean:
	@$(RM) -R $(OUTPUT) $(DATFILE) $(LSTFILE) $(SYMFILE) $(DSKFILE) $(FNTFILE)

build: $(OUTPUT) $(DATFILE) $(FNTFILE)

$(DATFILE): $(OUTPUT)

dsk: $(DSKFILE)

DSKCONT			= $(OUTPUT) $(DATFILE) $(FNTFILE) TEST.TXT AUTOEXEC.BAT S6ED.CFG

$(DSKFILE): $(DSKCONT)
	@cp $(DSKBASE) $(DSKFILE)
	@$(DSKTOOL) D $(DSKFILE) $(DSKCONT)
	@$(DSKTOOL) A $(DSKFILE) $(DSKCONT)

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

test:
	@$(TESTDIR)/runtests.py

selftest:
	@$(TESTDIR)/runtests.py --selftest

testall:
	@$(TESTDIR)/runtests.py --all
