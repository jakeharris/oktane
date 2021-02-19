import board
import digitalio

import random
import time

from src.hardware import KtaneHardware

# CONSTANTST
DEBOUNCE_TIMEOUT = 0.1  # in seconds. as low as we can go right now :(
IMMEDIATE_RELEASE_TIMEOUT = 0.5  # in seconds
BUTTON_TEXTS = ["abort", "detonate", "hold", "press"]
BUTTON_COLORS = ["blue", "white", "black", "red", "yellow"]
RELEVANT_INDICATORS = ["CAR", "FRK"]
STRIP_COLORS = ["blue", "red", "white", "yellow"]
ADDRESS = 0x10

BUTTON_PIN = board.D5


class Button(KtaneHardware):

    text = ""
    buttonColor = ""
    batteryCount = 0
    litIndicators = []
    stripColor = ""

    buttonPin = None

    wasButtonPressed = False
    buttonPressedAt = None  # timestamp

    def __init__(self):
        super().__init__(ADDRESS)

        # game state
        self.text = random.choice(BUTTON_TEXTS)
        self.buttonColor = random.choice(BUTTON_COLORS)
        self.stripColor = random.choice(STRIP_COLORS)
        self.batteryCount = fetchBatteryCount()
        self.litIndicators = fetchLitIndicators(RELEVANT_INDICATORS)

        # hardware setup
        self.buttonPin = digitalio.DigitalInOut(BUTTON_PIN)
        self.buttonPin.direction = digitalio.Direction.INPUT
        self.buttonPin.pull = digitalio.Pull.UP

    def isButtonPressed(self):
        return self.buttonPin.value == False

    def loop(self):
        # read stuff:
        # handle seq num stuff (super()?)
        # poll()

        self.poll()

        isButtonPressed = self.isButtonPressed()

        if isButtonPressed and not self.wasButtonPressed:
            self.buttonPressedAt = time.monotonic()
            print(self.stripColor)

        if not isButtonPressed and self.wasButtonPressed:
            # debounce
            if time.monotonic() - self.buttonPressedAt <= DEBOUNCE_TIMEOUT:
                return

            if self.isGoodButtonRelease():
                self.disarmed()
            else:
                self.strike()

        self.wasButtonPressed = isButtonPressed

    def isGoodButtonRelease(self):
        isImmediateRelease = (
            time.monotonic() - self.buttonPressedAt <= IMMEDIATE_RELEASE_TIMEOUT
        )

        if self.buttonColor == "blue" and self.text == "abort":
            if not isImmediateRelease:
                return self.isGoodHoldRelease()

        elif self.batteryCount > 1 and self.text == "detonate":
            return isImmediateRelease

        elif self.buttonColor == "white" and "CAR" in self.litIndicators:
            if not isImmediateRelease:
                return self.isGoodHoldRelease()

        elif self.batteryCount > 2 and "FRK" in self.litIndicators:
            return isImmediateRelease

        elif self.buttonColor == "yellow":
            if not isImmediateRelease:
                return self.isGoodHoldRelease()

        elif self.buttonColor == "red" and self.text == "hold":
            return isImmediateRelease

        else:
            if not isImmediateRelease:
                return self.isGoodHoldRelease()

        return False

    def isGoodHoldRelease(self):
        # @todo: request timer value, not this module's uptime
        if self.stripColor == "blue":
            return self.isDigitInTime(4)
        if self.stripColor == "yellow":
            return self.isDigitInTime(5)

        return self.isDigitInTime(1)

    def isDigitInTime(self, digit):
        # @todo: consider RTT for fetching timer value. may want to
        #   take timestamp before and after fetch, and subtract
        time = fetchTime()
        digitStr = str(digit)
        return digitStr in time


def fetchBatteryCount() -> int:
    # @todo: send request for battery count to main board
    return random.randint(0, 3)


def fetchLitIndicators(indicators: list) -> list:
    # @todo: send request for each indicator to main board
    #        if main board says it's lit, add it to return array
    indicatorSetIndex = random.randint(0, 3)
    if indicatorSetIndex == 0:
        return []
    if indicatorSetIndex == 1:
        return ["CAR"]
    if indicatorSetIndex == 2:
        return ["FRK"]
    if indicatorSetIndex == 3:
        return ["CAR", "FRK"]


def fetchTime() -> str:
    # @todo fetch from timer module
    currentTime = time.monotonic()  # seconds
    minutes = int(currentTime / 60)
    seconds = int(currentTime - (60 * minutes))
    timeStr = str(minutes) + ":" + str(seconds)
    return timeStr


button = Button()

print(button.buttonColor, button.text)
print(str(button.batteryCount) + " batteries, ", button.litIndicators)

timerPrintTimeout = 1  # in s
lastPrintTime = time.monotonic()

while True:
    button.loop()
    if time.monotonic() - lastPrintTime > timerPrintTimeout:
        print(fetchTime())
        lastPrintTime = time.monotonic()