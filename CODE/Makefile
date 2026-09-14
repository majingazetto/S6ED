#	*************************************************************************
#	* S6ED MSX2 Screen 6 Text Editor					 	                *
#	* (c) 2024 - 2025 Armando Pérez            						    	*
#	*************************************************************************

.PHONY: build run clean

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

# FONTBIN=1 uses the bundled RES/FONTS.BIN instead of the MSX ROM charset (default: 1).
FONTBIN			?= 1
ifeq ($(FONTBIN),1)
DEFINES			+= -D_FONTBIN_
endif

DSKFILE			= S6ED.DSK
DSKTOOL			= ../../msxtools/bin/dsktool
DSKBASE			= $(RES_DIR)/DOS2.DSK

# -	 All Target --------------------------------------------------------------

all: build dsk

# -	 Clean Target ------------------------------------------------------------

clean:
	@$(RM) -R $(OUTPUT) $(LSTFILE) $(SYMFILE) $(DSKFILE)

build: $(OUTPUT)

dsk: $(DSKFILE)

$(DSKFILE): $(OUTPUT) TEST.TXT AUTOEXEC.BAT S6ED.CFG
	@cp $(DSKBASE) $(DSKFILE)
	@$(DSKTOOL) D $(DSKFILE) $(OUTPUT) TEST.TXT AUTOEXEC.BAT S6ED.CFG
	@$(DSKTOOL) A $(DSKFILE) $(OUTPUT) TEST.TXT AUTOEXEC.BAT S6ED.CFG

# -	 Build Target ------------------------------------------------------------

$(RES_DIR)/FONTS.BIN: $(RES_DIR)/FONT.PNG $(RES_DIR)/fontcheck.py
	python3 $(RES_DIR)/fontcheck.py $< --variant normal --out $(RES_DIR)/FONT_NORM.BIN
	python3 $(RES_DIR)/fontcheck.py $< --variant bold --out $(RES_DIR)/FONT_BOLD.BIN
	python3 $(RES_DIR)/fontcheck.py $< --variant italic --out $(RES_DIR)/FONT_ITAL.BIN
	python3 $(RES_DIR)/fontcheck.py $< --variant bolditalic --out $(RES_DIR)/FONT_BI.BIN
	cat $(RES_DIR)/FONT_NORM.BIN $(RES_DIR)/FONT_BOLD.BIN $(RES_DIR)/FONT_ITAL.BIN $(RES_DIR)/FONT_BI.BIN > $@
	@$(RM) $(RES_DIR)/FONT_NORM.BIN $(RES_DIR)/FONT_BOLD.BIN $(RES_DIR)/FONT_ITAL.BIN $(RES_DIR)/FONT_BI.BIN

$(OUTPUT): $(ALL_SOURCES_GEN) $(RES_DIR)/FONTS.BIN
	@$(ASM) --lst=$(LSTFILE) --sym=$(SYMFILE) $(INCLUDES) $(DEFINES) $(MAIN)

# -	 Run Targets -------------------------------------------------------------

run: build dsk
	m2d2 $(DSKFILE)

# Minimum-spec check: stock 128 kB Philips NMS 8250
run128: build dsk
	m2d2 128k $(DSKFILE)

# Debug build, with the DBG trace captured from the openMSX debug device
debug:
	@$(MAKE) DEBUG=1 build dsk
	m2d2 $(DSKFILE) -ext debugdevice

log:
	@echo $(ALL_SOURCES_GEN)
