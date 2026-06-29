cmake_minimum_required(VERSION 3.20)
project(dronezone_firmware C CXX ASM)

# ── Toolchain ARM GCC ─────────────────────────────────────────
set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR ARM)
set(CMAKE_C_COMPILER   arm-none-eabi-gcc)
set(CMAKE_CXX_COMPILER arm-none-eabi-g++)
set(CMAKE_ASM_COMPILER arm-none-eabi-gcc)
set(CMAKE_OBJCOPY      arm-none-eabi-objcopy)
set(CMAKE_SIZE         arm-none-eabi-size)

# ── Target: STM32H743 ─────────────────────────────────────────
set(CPU_FLAGS "-mcpu=cortex-m7 -mthumb -mfpu=fpv5-d16 -mfloat-abi=hard")
set(CMAKE_C_FLAGS   "${CPU_FLAGS} -Wall -Wextra -O2 -ffunction-sections -fdata-sections")
set(CMAKE_CXX_FLAGS "${CMAKE_C_FLAGS} -std=c++17 -fno-exceptions -fno-rtti")
set(CMAKE_EXE_LINKER_FLAGS "${CPU_FLAGS} -T${CMAKE_SOURCE_DIR}/STM32H743xx.ld -Wl,--gc-sections -specs=nano.specs")

# ── Defines ───────────────────────────────────────────────────
add_definitions(
    -DSTM32H743xx
    -DUSE_HAL_DRIVER
    -DARM_MATH_CM7
    -DFIRMWARE_VERSION="1.0.0"
)

# ── Include paths ─────────────────────────────────────────────
include_directories(
    firmware/
    libs/STM32H7xx_HAL_Driver/Inc
    libs/CMSIS/Include
    libs/CMSIS/Device/ST/STM32H7xx/Include
    libs/FreeRTOS/Source/include
    libs/FreeRTOS/Source/portable/GCC/ARM_CM7/r0p1
    libs/mavlink/v2.0
)

# ── Surse firmware ────────────────────────────────────────────
file(GLOB_RECURSE FW_SOURCES
    "firmware/core/*.cpp"
    "firmware/sensors/*.cpp"
    "firmware/motors/*.cpp"
    "firmware/pid/*.cpp"
    "firmware/telemetry/*.cpp"
    "firmware/failsafe/*.cpp"
    "firmware/relay/*.cpp"
)

# ── Surse HAL + FreeRTOS ─────────────────────────────────────
file(GLOB HAL_SOURCES "libs/STM32H7xx_HAL_Driver/Src/*.c")
file(GLOB RTOS_SOURCES
    "libs/FreeRTOS/Source/*.c"
    "libs/FreeRTOS/Source/portable/GCC/ARM_CM7/r0p1/port.c"
    "libs/FreeRTOS/Source/portable/MemMang/heap_4.c"
)

# ── Executabil ────────────────────────────────────────────────
add_executable(dronezone.elf
    firmware/startup/startup_stm32h743xx.s
    ${FW_SOURCES}
    ${HAL_SOURCES}
    ${RTOS_SOURCES}
)

# ── Generare .bin pentru flash ────────────────────────────────
add_custom_command(TARGET dronezone.elf POST_BUILD
    COMMAND ${CMAKE_OBJCOPY} -O binary dronezone.elf dronezone.bin
    COMMAND ${CMAKE_SIZE} dronezone.elf
    COMMENT "Generare dronezone.bin pentru flashare"
)

# ── Flash pe placă (cu OpenOCD / ST-Link) ─────────────────────
add_custom_target(flash
    COMMAND openocd -f interface/stlink.cfg -f target/stm32h7x.cfg
            -c "program dronezone.bin 0x08000000 verify reset exit"
    DEPENDS dronezone.elf
    COMMENT "Flashare firmware pe STM32H743"
)
