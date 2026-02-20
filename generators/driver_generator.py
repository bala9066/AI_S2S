"""Driver Generator - C/C++ code generation for hardware drivers."""

import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


class DriverGenerator:
    """Generate C driver code from hardware specifications."""

    def generate(self, project_name: str, components: List[Dict], registers: List[Dict], metadata: Dict = None) -> Dict[str, str]:
        return {
            "hal.h": self._generate_header(project_name),
            "hal.c": self._generate_source(project_name),
            "Makefile": self._generate_makefile(project_name),
        }

    def _generate_header(self, project_name: str) -> str:
        safe_name = project_name.replace(" ", "_").lower()
        guard = f"{safe_name}_HAL_H"
        return f"""/**
 * @file hal.h
 * @brief Hardware Abstraction Layer for {project_name}
 */

#ifndef {guard}
#define {guard}

#include <stdint.h>
#include <stdbool.h>

typedef enum {{
    HAL_OK = 0,
    HAL_ERROR = -1,
    HAL_BUSY = -2,
}} hal_status_t;

typedef struct {{
    uint32_t clock_rate;
    uint32_t timeout_ms;
}} hal_config_t;

hal_status_t hal_init(void);
hal_status_t hal_deinit(void);

#endif /* {guard} */
"""

    def _generate_source(self, project_name: str) -> str:
        return f"""/**
 * @file hal.c
 * @brief Hardware Abstraction Layer implementation for {project_name}
 */

#include "hal.h"

static hal_config_t g_config = {{0}};
static bool g_initialized = false;

hal_status_t hal_init(void) {{
    if (g_initialized) return HAL_OK;
    g_config.clock_rate = 48000000;
    g_config.timeout_ms = 100;
    g_initialized = true;
    return HAL_OK;
}}

hal_status_t hal_deinit(void) {{
    g_initialized = false;
    return HAL_OK;
}}
"""

    def _generate_makefile(self, project_name: str) -> str:
        target = project_name.replace(" ", "_").lower()
        return f"""# Makefile for {project_name}

CC = gcc
CFLAGS = -Wall -Wextra -O2 -std=c11
LDFLAGS =

SRCDIR = src
OBJDIR = obj
SOURCES = $(wildcard $(SRCDIR)/*.c)
OBJECTS = $(SOURCES:$(SRCDIR)/%.c=$(OBJDIR)/%.o)
TARGET = {target}_driver

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(OBJECTS)
\t$(CC) $(LDFLAGS) -o $@ $^

$(OBJDIR)/%.o: $(SRCDIR)/%.c
\t@mkdir -p $(OBJDIR)
\t$(CC) $(CFLAGS) -c $< -o $@

clean:
\trm -rf $(OBJDIR) $(TARGET)
"""

    def save(self, files: Dict[str, str], output_dir: Path) -> List[Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        src_dir = output_dir / "src"
        src_dir.mkdir(exist_ok=True)
        
        saved = []
        for filename, content in files.items():
            filepath = output_dir / filename if filename == "Makefile" else src_dir / filename
            filepath.write_text(content, encoding="utf-8")
            saved.append(filepath)
        return saved
