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

DEFINES			= -DON=1\
				  -DOFF=0\
				  -DDEBUG=$(DEBUG)\
				  -DFINAL=$(FINAL)\

DSKFILE			= S6ED.DSK
DSKTOOL			= ../../MSXTOOLS/bin/dsktool
DSKBASE			= $(RES_DIR)/DOS2.DSK

# -	 All Target --------------------------------------------------------------

all: build dsk

# -	 Clean Target ------------------------------------------------------------

clean:
	@$(RM) -R $(OUTPUT) $(LSTFILE) $(SYMFILE) $(DSKFILE)

build: $(OUTPUT)

dsk: $(DSKFILE)

$(DSKFILE): $(OUTPUT) TEST.TXT
	@cp $(DSKBASE) $(DSKFILE)
	@$(DSKTOOL) D $(DSKFILE) $(OUTPUT) TEST.TXT
	@$(DSKTOOL) A $(DSKFILE) $(OUTPUT) TEST.TXT

# -	 Build Target ------------------------------------------------------------

$(OUTPUT): $(ALL_SOURCES_GEN)
	@$(ASM) --lst=$(LSTFILE) --sym=$(SYMFILE) $(INCLUDES) $(DEFINES) $(MAIN)

run: build dsk
	msxtr $(DSKFILE)

log:
	@echo $(ALL_SOURCES_GEN)
