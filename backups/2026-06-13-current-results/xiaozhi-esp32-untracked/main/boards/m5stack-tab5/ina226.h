#ifndef INA226_H
#define INA226_H

#include "../common/i2c_device.h"

#include <esp_err.h>
#include <esp_log.h>

static const char* INA226_TAG = "Ina226";

class Ina226 : public I2cDevice {
public:
    Ina226(i2c_master_bus_handle_t i2c_bus, uint8_t addr = 0x41)
        : I2cDevice(i2c_bus, addr) {}

    // Read bus voltage in millivolts. Returns -1 on error.
    int ReadBusVoltageMv() {
        uint16_t raw = 0;
        esp_err_t err = ReadReg16(0x02, raw);
        if (err != ESP_OK) {
            ESP_LOGW(INA226_TAG, "Failed to read bus voltage: %s", esp_err_to_name(err));
            return -1;
        }

        // INA226 bus voltage register is 1.25mV/LSB. Unlike INA219, it is not
        // shifted right by 3 bits.
        return (int)((raw * 125 + 50) / 100);
    }

    // Read shunt voltage in microvolts.
    // Tab5 wiring: shunt V+ on battery side, V- on charger/load side.
    // Positive = current flowing from battery TO load (DISCHARGING).
    // Negative = current flowing from charger TO battery (CHARGING).
    // 2.5uV/LSB, 16-bit signed. Tab5 shunt resistor: 0.005Ω.
    int ReadShuntVoltageUv() {
        uint16_t raw_u16 = 0;
        esp_err_t err = ReadReg16(0x01, raw_u16);
        if (err != ESP_OK) {
            ESP_LOGW(INA226_TAG, "Failed to read shunt voltage: %s", esp_err_to_name(err));
            return 0;
        }

        int16_t raw = static_cast<int16_t>(raw_u16);
        return (int)((raw * 25) / 10);
    }

    esp_err_t ReadRawBusVoltage(uint16_t& raw) {
        return ReadReg16(0x02, raw);
    }

    esp_err_t ReadRawShuntVoltage(int16_t& raw) {
        uint16_t raw_u16 = 0;
        esp_err_t err = ReadReg16(0x01, raw_u16);
        raw = static_cast<int16_t>(raw_u16);
        return err;
    }

private:
    esp_err_t ReadReg16(uint8_t reg, uint16_t& value) {
        uint8_t buffer[2] = {0};
        esp_err_t err = i2c_master_transmit_receive(i2c_device_, &reg, 1, buffer, sizeof(buffer), 100);
        if (err != ESP_OK) {
            return err;
        }
        value = (static_cast<uint16_t>(buffer[0]) << 8) | buffer[1];
        return ESP_OK;
    }
};

#endif // INA226_H
