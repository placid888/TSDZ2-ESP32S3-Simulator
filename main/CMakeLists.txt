idf_component_register(SRCS "main.c" "tsdz_utils.c"
INCLUDE_DIRS "."
REQUIRES driver freertos esp_timer nvs_flash bt nimble)