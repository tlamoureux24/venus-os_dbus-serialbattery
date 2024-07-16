#!/usr/bin/python
# -*- coding: utf-8 -*-
import sys
from time import sleep
from typing import Union

# import dbus and gobject
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib as gobject

# import driver classes
from dbushelper import DbusHelper
from utils import logger
import utils
from battery import Battery

# import battery classes
from bms.daly import Daly
from bms.ecs import Ecs
from bms.eg4_lifepower import EG4_Lifepower
from bms.eg4_ll import EG4_LL
from bms.heltecmodbus import HeltecModbus
from bms.hlpdatabms4s import HLPdataBMS4S
from bms.jkbms import Jkbms
from bms.jkbms_pb import Jkbms_pb
from bms.lltjbd import LltJbd
from bms.renogy import Renogy
from bms.seplos import Seplos
from bms.seplosv3 import Seplosv3

# enabled only if explicitly set in config under "BMS_TYPE"
if "ANT" in utils.BMS_TYPE:
    from bms.ant import ANT
if "MNB" in utils.BMS_TYPE:
    from bms.mnb import MNB
if "Sinowealth" in utils.BMS_TYPE:
    from bms.sinowealth import Sinowealth

supported_bms_types = [
    {"bms": Daly, "baud": 9600, "address": b"\x40"},
    {"bms": Daly, "baud": 9600, "address": b"\x80"},
    {"bms": Ecs, "baud": 19200},
    {"bms": EG4_Lifepower, "baud": 9600, "address": b"\x01"},
    {"bms": EG4_LL, "baud": 9600, "address": b"\x01"},
    {"bms": HeltecModbus, "baud": 9600, "address": b"\x01"},
    {"bms": HLPdataBMS4S, "baud": 9600},
    {"bms": Jkbms, "baud": 115200},
    {"bms": Jkbms_pb, "baud": 115200, "address": b"\x01"},
    {"bms": LltJbd, "baud": 9600},
    {"bms": Renogy, "baud": 9600, "address": b"\x30"},
    {"bms": Renogy, "baud": 9600, "address": b"\xF7"},
    {"bms": Seplos, "baud": 19200, "address": b"\x00"},
    {"bms": Seplosv3, "baud": 19200},
]

# enabled only if explicitly set in config under "BMS_TYPE"
if "ANT" in utils.BMS_TYPE:
    supported_bms_types.append({"bms": ANT, "baud": 19200})
if "MNB" in utils.BMS_TYPE:
    supported_bms_types.append({"bms": MNB, "baud": 9600})
if "Sinowealth" in utils.BMS_TYPE:
    supported_bms_types.append({"bms": Sinowealth, "baud": 9600})

expected_bms_types = [
    battery_type
    for battery_type in supported_bms_types
    if battery_type["bms"].__name__ in utils.BMS_TYPE or len(utils.BMS_TYPE) == 0
]

logger.info("")
logger.info("Starting dbus-serialbattery")


def main():
    # NameError: free variable 'expected_bms_types' referenced before assignment in enclosing scope
    global expected_bms_types

    def poll_battery(loop):
        helper.publish_battery(loop)
        return True

    def get_battery(_port) -> Union[Battery, None]:
        # all the different batteries the driver support and need to test for
        # try to establish communications with the battery 3 times, else exit
        retry = 1
        retries = 3
        while retry <= retries:
            logger.info(
                "-- Testing BMS: " + str(retry) + " of " + str(retries) + " rounds"
            )
            # create a new battery object that can read the battery and run connection test
            for test in expected_bms_types:
                # noinspection PyBroadException
                try:
                    logger.info(
                        "Testing "
                        + test["bms"].__name__
                        + (
                            ' at address "'
                            + utils.bytearray_to_string(test["address"])
                            + '"'
                            if "address" in test
                            else ""
                        )
                    )
                    batteryClass = test["bms"]
                    baud = test["baud"]
                    battery: Battery = batteryClass(
                        port=_port, baud=baud, address=test.get("address")
                    )
                    if battery.test_connection() and battery.validate_data():
                        logger.info(
                            "Connection established to " + battery.__class__.__name__
                        )
                        return battery
                except KeyboardInterrupt:
                    return None
                except Exception:
                    (
                        exception_type,
                        exception_object,
                        exception_traceback,
                    ) = sys.exc_info()
                    file = exception_traceback.tb_frame.f_code.co_filename
                    line = exception_traceback.tb_lineno
                    logger.error(
                        "Non blocking exception occurred: "
                        + f"{repr(exception_object)} of type {exception_type} in {file} line #{line}"
                    )
                    # Ignore any malfunction test_function()
                    pass
            retry += 1
            sleep(0.5)

        return None

    def get_port() -> str:
        # Get the port we need to use from the argument
        if len(sys.argv) > 1:
            port = sys.argv[1]
            if port not in utils.EXCLUDED_DEVICES:
                return port
            else:
                logger.debug(
                    "Stopping dbus-serialbattery: "
                    + str(port)
                    + " is excluded trough the config file"
                )
                sleep(60)
                # exit with error in order that the serialstarter goes on
                sys.exit(1)
        else:
            # just for MNB-SPI
            logger.info("No Port needed")
            return "/dev/ttyUSB9"

    # read the version of Venus OS
    with open("/opt/victronenergy/version", "r") as f:
        venus_version = f.readline().strip()
    # show Venus OS version
    logger.info("Venus OS " + venus_version)

    # show the version of the driver
    logger.info("dbus-serialbattery v" + str(utils.DRIVER_VERSION))

    port = get_port()
    battery = None

    # wait some seconds to be sure that the serial connection is ready
    # else the error throw a lot of timeouts
    sleep(16)

    if port.endswith("_Ble"):
        """
        Import ble classes only, if it's a ble port, else the driver won't start due to missing python modules
        This prevent problems when using the driver only with a serial connection
        """

        if len(sys.argv) <= 2:
            logger.error("missing bluetooth address")
        else:
            ble_address = sys.argv[2]

            if port == "Jkbms_Ble":
                # noqa: F401 --> ignore flake "imported but unused" error
                from bms.jkbms_ble import Jkbms_Ble  # noqa: F401

            if port == "LltJbd_Ble":
                # noqa: F401 --> ignore flake "imported but unused" error
                from bms.lltjbd_ble import LltJbd_Ble  # noqa: F401

            class_ = eval(port)
            # do not remove ble_ prefix, since the dbus service cannot be only numbers
            testbms = class_(
                "ble_" + ble_address.replace(":", "").lower(), 9600, ble_address
            )
            if testbms.test_connection():
                logger.info("Connection established to " + testbms.__class__.__name__)
                battery = testbms

    elif port.startswith("can"):
        """
        Import CAN classes only, if it's a can port, else the driver won't start due to missing python modules
        This prevent problems when using the driver only with a serial connection
        """
        from bms.daly_can import Daly_Can
        from bms.jkbms_can import Jkbms_Can

        # only try CAN BMS on CAN port
        supported_bms_types = [
            {"bms": Daly_Can, "baud": 250000},
            {"bms": Jkbms_Can, "baud": 250000},
        ]

        expected_bms_types = [
            battery_type
            for battery_type in supported_bms_types
            if battery_type["bms"].__name__ in utils.BMS_TYPE
            or len(utils.BMS_TYPE) == 0
        ]

        battery = get_battery(port)

    else:
        battery = get_battery(port)

    # exit if no battery could be found
    if battery is None:
        logger.error("ERROR >>> No battery connection at " + port)
        sys.exit(1)

    # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
    DBusGMainLoop(set_as_default=True)
    if sys.version_info.major == 2:
        gobject.threads_init()
    mainloop = gobject.MainLoop()

    # Get the initial values for the battery used by setup_vedbus
    helper = DbusHelper(battery)

    if not helper.setup_vedbus():
        logger.error("ERROR >>> Problem with battery set up at " + port)
        sys.exit(1)

    # try using active callback on this battery
    if not battery.use_callback(lambda: poll_battery(mainloop)):
        # change poll interval if set in config
        if utils.POLL_INTERVAL is not None:
            battery.poll_interval = utils.POLL_INTERVAL
        # if not possible, poll the battery every poll_interval milliseconds
        gobject.timeout_add(battery.poll_interval, lambda: poll_battery(mainloop))

    # print log at this point, else not all data is correctly populated
    battery.log_settings()

    # check config, if there are any invalid values trigger "settings incorrect" error
    if not utils.validate_config_values():
        battery.state = 10
        battery.error_code = 119

    # use external current sensor if configured
    try:
        if (
            utils.EXTERNAL_CURRENT_SENSOR_DBUS_DEVICE is not None
            and utils.EXTERNAL_CURRENT_SENSOR_DBUS_PATH is not None
        ):
            battery.monitor_external_current()
    except Exception:
        # set to None to avoid crashing, fallback to battery current
        utils.EXTERNAL_CURRENT_SENSOR_DBUS_DEVICE = None
        utils.EXTERNAL_CURRENT_SENSOR_DBUS_PATH = None
        (
            exception_type,
            exception_object,
            exception_traceback,
        ) = sys.exc_info()
        file = exception_traceback.tb_frame.f_code.co_filename
        line = exception_traceback.tb_lineno
        logger.error(
            "Exception occurred: "
            + f"{repr(exception_object)} of type {exception_type} in {file} line #{line}"
        )

    # Run the main loop
    try:
        mainloop.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
