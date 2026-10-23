idf_component_register(SRCS "main.c" "tsdz_utils.c" "bench_model.c" "bench_app.c" "dac8568.c"
INCLUDE_DIRS "."
REQUIRES json esp_app_format driver freertos esp_timer nvs_flash bt )
