"""
Support for Piglow LED's.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/light.piglow/
"""
import logging
import time

import voluptuous as vol

import homeassistant.components.rpi_gpio as rpi_gpio
import homeassistant.helpers.config_validation as cv
from homeassistant.components.light import (
    ATTR_BRIGHTNESS, SUPPORT_BRIGHTNESS, ATTR_RGB_COLOR, SUPPORT_RGB_COLOR,
    Light, PLATFORM_SCHEMA)
from homeassistant.const import CONF_NAME

_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = ['rpi_gpio']

DEFAULT_NAME = "LED"
MODE_SINGLE = "single"
MODE_RGB = "rgb"
FREQUENCY = 100

STEPS = 20
DELAY = 0.01

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required("mode"): vol.Any(MODE_SINGLE, MODE_RGB),
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Required("ports"): vol.All(cv.ensure_list, [vol.Coerce(int)]),
})

# pylint: disable=unused-argument
def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the Piglow Light platform."""
    _LOGGER.info("Setting up rpi_led")

    name = config.get(CONF_NAME)
    mode = config.get("mode")
    ports = config.get("ports")

    if mode == MODE_SINGLE and len(ports) != 1 \
            or mode == MODE_RGB and len(ports) != 3:
        _LOGGER.error("Incorrect number of ports given for device \"%s\". "
                      "It will not be added", name)
        return False
    else:
        add_devices([LED(name, mode, ports)])


class LED(Light):
    """Representation of an Piglow Light."""

    def __init__(self, name, mode, ports):
        """Initialize an PiglowLight."""
        self._name = name
        self._mode = mode
        self._is_on = False
        self._brightness = 0
        self._rgb_color = [255, 255, 255]
        self._current_dc = [None, None, None]
        if mode == MODE_RGB:
            self._features = (SUPPORT_BRIGHTNESS | SUPPORT_RGB_COLOR)
        else:
            self._features = SUPPORT_BRIGHTNESS

        # init GPIO and PWM
        for port in ports:
            rpi_gpio.setup_output(port)

        self._pwm = [rpi_gpio.init_pwm(port, FREQUENCY) for port in ports]


    @property
    def name(self):
        """Return the display name of this light."""
        return self._name

    @property
    def brightness(self):
        """Brightness of the light (an integer in the range 1-255)."""
        return self._brightness

    @property
    def rgb_color(self):
        """Read back the color of the light."""
        return self._rgb_color

    @property
    def supported_features(self):
        """Flag supported features."""
        return self._features

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._is_on

    def set_pwm(self, idx, dutycycle):
        if dutycycle > 100:
            dutycycle = 100
        elif dutycycle < 0:
            dutycycle = 0

        _LOGGER.debug("Called set_pwm[%d] = %f", idx, dutycycle)

        if self._current_dc[idx] is not None:
            self._pwm[idx].ChangeDutyCycle(dutycycle)
        else:
            self._pwm[idx].start(dutycycle)

        self._current_dc[idx] = dutycycle

    def fade_single(self, brightness):
        current_bright = self._current_dc[0]
        new_bright = brightness * 100

        delta = new_bright - current_bright

        for _ in range(STEPS):
            self.set_pwm(0, current_bright+(delta/STEPS))
            time.sleep(DELAY)


    def fade_rgb(self, brightness, color):
        _LOGGER.debug("Called fade_rgb: brightness  %f, color %s", brightness, color)
        _LOGGER.debug("Current: b: %d, c: %s", self._brightness, self._rgb_color)
        current_brightness = self._brightness / 255
        delta = []
        for i in range(3):
            delta.append((color[i]*brightness - self._rgb_color[i]*current_brightness) * 100 / 255 / STEPS)

        _LOGGER.debug("Delta: %s", delta)

        current_dc = []
        for dutycycle in self._current_dc:
            if dutycycle is None:
                current_dc.append(0.0)
            else:
                current_dc.append(dutycycle)

        actual_steps = STEPS * 2

        for i in range(actual_steps):
            for color in range(3):
                if (delta[color] > 0 and i < actual_steps/2) or (delta[color] < 0 and i >= actual_steps/2):
                    self.set_pwm(color, current_dc[color] + delta[color]*(i+1))

            time.sleep(DELAY)

    def turn_on(self, **kwargs):
        """Instruct the light to turn on."""
        brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
        percent_bright = brightness / 255

        if self._mode == MODE_RGB:
            if ATTR_RGB_COLOR in kwargs:
                new_color = kwargs[ATTR_RGB_COLOR]
            else:
                new_color = self._rgb_color

            self.fade_rgb(percent_bright, new_color)
            self._rgb_color = new_color
            self._brightness = brightness
        else:
            self.fade_single(percent_bright)
            self._brightness = brightness


        self._is_on = True

    def turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        for pwm in self._pwm:
            pwm.stop()

        self._brightness = 0
        self._current_dc = [None, None, None]        
        self._is_on = False
