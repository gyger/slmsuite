"""
Hardware control for Thorlabs cameras via :mod:`TLCameraSDK`.
The :mod:`thorlabs_tsi_sdk` module must
be installed (See [1]_ -> Programming Interfaces). Consider also installing ThorCam
for testing cameras outside of Python (See [1]_ -> Software).
After installing the SDK, extract the files in:
``~\\Program Files\\Thorlabs\\Scientific Imaging\\Scientific Camera Support\\Scientific_Camera_Interfaces.zip``.
Follow the instructions in Python_README.txt.

References
----------
.. [1] https://www.thorlabs.com/software_pages/ViewSoftwarePage.cfm?Code=ThorCam
"""

import os
import sys
import time

from slmsuite.hardware.cameras.camera import Camera

def configure_tlcam_dll_path(
    dll_path=(  "C:\\Program Files\\Thorlabs\\Scientific Imaging\\"
                "Scientific Camera Support\\Scientific Camera "
                "Interfaces\\SDK\\Native Toolkit\\dlls\\Native_"    )):
    """
    Adds Thorlabs camera DLLs to the DLL path.

    Parameters
    ----------
    dll_path : str
        Full path to the Thorlabs camera DLLs.
    """
    is_64bits = sys.maxsize > 2 ** 32

    if is_64bits:
        dll_path += "64_lib"
    else:
        dll_path += "32_lib"

    os.environ["PATH"] = dll_path + os.pathsep + os.environ["PATH"]

    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(dll_path)
        except BaseException as e:
            print("thorlabs_tsi_sdk DLL not found. Resolve to use Thorlabs cameras.")
    else:
        print("thorlabs.py: os has no attribute add_dll_directory.")

configure_tlcam_dll_path()
try:
    from thorlabs_tsi_sdk.tl_camera import TLCameraSDK, ROI
except ImportError:
    print("thorlabs_tsi_sdk not installed. Install to use Thorlabs cameras.")


class ThorCam(Camera):
    """
    Thorlabs camera.

    Attributes
    ----------
    sdk : TLCameraSDK
        Object to talk with the Thorlabs SDK. Shared among instances of :class:`ThorCam`.
    cam : ThorCam
        Object to talk with the desired camera.
    profile : {'free', 'single', 'single_hardware'} or None
        Current operation mode.\n
        'free' means always capturing.\n
        'single' means only gets frame on command.\n
        'single_hardware' means only gets frame on hardware trigger or command.\n
        None means camera is disarmed.
    """

    sdk = None

    ### Initialization and termination ###

    def __init__(self, serial="", verbose=True, **kwargs):
        """
        Initialize camera and attributes. Initial profile is ``"single"``.

        Parameters
        ----------
        serial : str
            Serial number of the camera to open. If empty, defaults to the first camera in the list
            returned by :meth:`TLCameraSDK.discover_available_cameras()`.
        verbose : bool
            Whether or not to print extra information.
        kwargs
            See :meth:`.Camera.__init__` for permissible options.

        Raises
        ------
        RuntimeError
           If the camera can not be reached.
        """
        if ThorCam.sdk is None:
            if verbose:
                print("TLCameraSDK initializing... ", end="")
            ThorCam.sdk = TLCameraSDK()
            if verbose:
                print("success")

        if verbose:
            print("Looking for cameras... ", end="")
        camera_list = ThorCam.sdk.discover_available_cameras()
        if verbose:
            print("success")

        if serial == "":
            if len(camera_list) == 0:
                raise RuntimeError("No cameras found by TLCameraSDK.")
            serial = camera_list[0]
        elif serial not in camera_list:
            raise RuntimeError(
                "Serial " + serial + " not found by TLCameraSDK. Availible: ",
                camera_list,
            )

        if verbose:
            print("ThorCam sn \"{}\" initializing... ".format(serial), end="")
        self.cam = ThorCam.sdk.open_camera(serial)

        self.cam.is_led_on = False

        # Initialize profile variable, then set to the proper value.
        self.profile = None
        self.setup("single")

        # Initialize binning to 1.
        self.set_binning()

        super().__init__(
            self.cam.image_width_pixels,
            self.cam.image_height_pixels,
            bitdepth=self.cam.bit_depth,
            dx_um=self.cam.sensor_pixel_width_um,
            dy_um=self.cam.sensor_pixel_height_um,
            name=serial,
            **kwargs
        )

        if verbose:
            print("success")

    def close(self, close_sdk=False):
        """
        See :meth:`.Camera.close`.

        Parameters
        ----------
        close_sdk : bool
            Whether or not to close the TLCameraSDK instance.
        """
        # Future: the proper way to treat sdk deletion would be
        # to keep a class-wide count of the number of open instances
        # and delete the sdk when the last instance is closed.
        # We would want to use a lock to do this.

        self.cam.dispose()

        if close_sdk:
            self.close_sdk()

    @staticmethod
    def info(verbose=True):
        """
        Discovers all Thorlabs scientific cameras.

        Parameters
        ----------
        verbose : bool
            Whether to print the discovered information.

        Returns
        --------
        list of (int, (int, int, int, int)) tuples
            The number and geometry of each display.
        """
        if ThorCam.sdk is None:
            ThorCam.sdk = TLCameraSDK()
            close_sdk = True
        else:
            close_sdk = False

        camera_list = ThorCam.sdk.discover_available_cameras()

        if verbose:
            print("ThorCam serials:")
            for serial in camera_list:
                print("\"{}\"".format(serial))

        if close_sdk:
            ThorCam.close_sdk()

        return camera_list

    @staticmethod
    def close_sdk():
        """
        Close the TLCameraSDK instance.
        """
        ThorCam.sdk.dispose()
        ThorCam.sdk = None

    def reset(self):
        """See :meth:`.Camera.reset`."""
        self.close()
        self.__init__()

    ### Property Configuration ###

    def get_exposure(self):
        """See :meth:`.Camera.get_exposure`."""
        return float(self.cam.exposure_time_us) / 1e6

    def set_exposure(self, exposure_s):
        """See :meth:`.Camera.set_exposure`."""
        self.cam.exposure_time_us = int(exposure_s * 1e6)

    def set_binning(self, bx=None, by=None):
        """
        Set the binning of the camera. Will error if a certain binning is not supported.

        Parameters
        ----------
        bx : int
            The binning value in the horizontal direction.
        by : int
            The binning value in the vertical direction.
        """
        # Save old profile and disarm
        profile = self.profile
        self.setup(None)

        if bx is None:
            bx = 1
        if by is None:
            by = 1
        self.cam.binx = int(bx)
        self.cam.biny = int(by)

        # Restore profile
        self.setup(profile)

    def set_woi(self, woi=None):
        """See :meth:`.Camera.set_woi`."""
        # Save old profile and disarm
        profile = self.profile
        self.setup(None)

        if woi is None:  # Default to maximum WOI
            woi = (
                self.cam.roi_range.upper_left_x_pixels_min,
                self.cam.roi_range.lower_right_x_pixels_max
                - self.cam.roi_range.upper_left_x_pixels_min,
                self.cam.roi_range.upper_left_y_pixels_min,
                self.cam.roi_range.lower_right_y_pixels_max
                - self.cam.roi_range.upper_left_y_pixels_min,
            )

        self.woi = woi

        newroi = ROI(
            self.cam.roi_range.lower_right_x_pixels_max - woi[0] - woi[1],
            woi[2],
            self.cam.roi_range.lower_right_x_pixels_max - woi[0],
            woi[2] + woi[3],
        )

        assert (
            self.cam.roi_range.upper_left_x_pixels_min
            <= newroi.upper_left_x_pixels
            <= self.cam.roi_range.upper_left_x_pixels_max
        )
        assert (
            self.cam.roi_range.upper_left_y_pixels_min
            <= newroi.upper_left_y_pixels
            <= self.cam.roi_range.upper_left_y_pixels_max
        )
        assert (
            self.cam.roi_range.lower_right_x_pixels_min
            <= newroi.lower_right_x_pixels
            <= self.cam.roi_range.lower_right_x_pixels_max
        )
        assert (
            self.cam.roi_range.lower_right_y_pixels_min
            <= newroi.lower_right_y_pixels
            <= self.cam.roi_range.lower_right_y_pixels_max
        )

        self.cam.roi = newroi

        self.woi = woi
        self.shape = (woi[3], woi[1])

        # Restore profile
        self.setup(profile)

        return woi

    def setup(self, profile):
        """
        Set operation mode.

        Parameters
        ----------
        profile
            See :attr:`profile`.
        """
        if profile != self.profile:
            if profile is None:
                self.cam.disarm()
            elif profile == "free":
                self.cam.disarm()
                self.cam.frames_per_trigger_zero_for_unlimited = 0
                self.cam.operation_mode = 0  # Software triggered
                self.cam.arm(2)
                self.cam.issue_software_trigger()
            elif profile == "single":
                self.cam.disarm()
                self.cam.frames_per_trigger_zero_for_unlimited = 1
                self.cam.operation_mode = 0  # Software triggered
                self.cam.arm(2)
            elif profile == "single_hardware":
                self.cam.disarm()
                self.cam.frames_per_trigger_zero_for_unlimited = 1
                self.cam.operation_mode = 1  # Hardware triggered
                self.cam.arm(2)
            else:
                raise ValueError("Profile {} not recognized".format(profile))

            self.profile = profile

    def get_image(self, timeout_s=1, trigger=True, grab=True):
        """
        See :meth:`.Camera.get_image`. By default ``trigger=True`` and ``grab=True`` which
        will result in blocking image acquisition.
        For non-blocking acquisition,
        set ``trigger=True`` and ``grab=False`` to issue a software trigger;
        then, call the method again with ``trigger=False`` and ``grab=True``
        to grab the resulting frame.

        Parameters
        ----------
        trigger : bool
            Whether or not to issue a software trigger.
        grab : bool
            Whehter or not to grab the frame (blocking).

        Returns
        -------
        numpy.ndarray or None
            Array of shape :attr:`shape` if ``grab=True``, else ``None``.
        """
        if trigger:
            if self.profile == "single":
                t = time.time()
                self.cam.issue_software_trigger()

        ret = None
        if grab:
            # Start the timer.
            if not trigger:
                t = time.time()

            frame = None

            # Try to grab a frame until we succeed.
            while time.time() - t < timeout_s and frame is None:
                frame = self.cam.get_pending_frame_or_null()

            ret = self.transform(frame.image_buffer) if frame is not None else None

        return ret

    def flush(self, timeout_s=1, verbose=False):
        """
        See :meth:`.Camera.flush`.

        Parameters
        ----------
        verbose : bool
            Whether or not to print extra information.
        """
        # Start the timer.
        t = time.perf_counter()

        ii = 0
        frame = self.cam.get_pending_frame_or_null()
        frametime = 0

        # Continue flushing frames while the timeout is not exceeded, the
        # returned frame is empty (None), or the frame returned super fast
        # (cached)
        while (
            time.perf_counter() - t < timeout_s
            and frame is not None
            and frametime < 0.003
        ):
            t2 = time.perf_counter()
            frame = self.cam.get_pending_frame_or_null()
            frametime = time.perf_counter() - t2
            ii += 1

        if verbose:
            print(
                "Flushed {} frames in {:.2f} ms".format(
                    ii, 1e3 * (time.perf_counter() - t)
                )
            )

    def is_capturing(self):
        """
        Determine whether or not the camera is currently capturing images.

        Returns
        -------
        bool
            Whether or not the camera is actively capturing images.
        """
        return self.profile == "free"
