"""Helper functions for processing images."""

import cv2
import numpy as np
import matplotlib.pyplot as plt
from functools import reduce
from scipy.ndimage import gaussian_filter1d as sp_gaussian_filter1d
from scipy.optimize import curve_fit

from slmsuite.holography.toolbox import format_2vectors
from slmsuite.misc.fitfunctions import gaussian2d


def take(images, vectors, size, centered=True, integrate=False, clip=False, plot=False):
    """
    Crop integration regions around an array of ``vectors``, yielding an array of images.

    Each integration region is a rectangle of the same ``size``. Similar to but more
    general than :meth:`numpy.take`; useful for gathering data from spots in spot arrays.

    Parameters
    ----------
    images : array_like
        2D image or array of 2D images.
    vectors : array_like of floats
        2-vector (or 2-vector array) listing location(s) of integration region(s).
        See :meth:`~slmsuite.holography.toolbox.format_2vectors`.
    size : int or (int, int)
        Size of the rectangular integration region in ``(w, h)`` format. If a scalar is given,
        assume square ``(w, w)``.
    centered : bool
        Whether to center the integration region on the ``vectors``.
        If ``False``, the lower left corner is used.
        Defaults to ``True``.
    integrate : bool
        If ``True``, the spatial dimension are integrated (summed), yielding a result of the
        same length as the number of vectors. Defaults to ``False``.
    clip : bool
        Whether to allow out-of-range integration regions. ``True`` allows regions outside
        the valid area, setting the invalid region to ``np.nan``
        (or zero if the array datatype does not support ``np.nan``).
        ``False`` throws an error upon out of range. Defaults to ``False``.
    plot : bool
        Calls :meth:`take_plot()` to visualize the images regions.

    Returns
    -------
    numpy.ndarray
        If ``integrate`` is ``False``, returns an array containing the images cropped
        from the regions of size `(image_count, h, w)`.
        If ``integrate`` is ``True``, instead returns an array of floats of size `(image_count,)`
        where each float corresponds to the :meth:`numpy.sum` of a cropped image.
    """
    # Clean variables.
    if isinstance(size, int):
        size = (size, size)

    vectors = format_2vectors(vectors)

    # Prepare helper variables. Future: consider caching for speed, if not negligible.
    edge_x = np.arange(size[0]) - (int(size[0] / 2) if centered else 0)
    edge_y = np.arange(size[1]) - (int(size[1] / 2) if centered else 0)

    region_x, region_y = np.meshgrid(edge_x, edge_y)

    integration_x = np.add(
        region_x.ravel()[:, np.newaxis].T, vectors[:][0][:, np.newaxis]
    ).astype(np.int)
    integration_y = np.add(
        region_y.ravel()[:, np.newaxis].T, vectors[:][1][:, np.newaxis]
    ).astype(np.int)

    shape = np.shape(images)

    if clip:  # Prevent out-of-range errors by clipping.
        mask = (
            (integration_x < 0)
            | (integration_x >= shape[-1])
            | (integration_y < 0)
            | (integration_y >= shape[-2])
        )

        # Clip these indices to prevent errors.
        np.clip(integration_x, 0, shape[-1] - 1, out=integration_x)
        np.clip(integration_y, 0, shape[-2] - 1, out=integration_y)
    else:
        pass  # Don't prevent out-of-range errors.

    # Take the data, depending on the
    if len(shape) == 2:
        result = images[np.newaxis, integration_y, integration_x]
    elif len(shape) == 3:
        result = images[:, integration_y, integration_x]
    else:
        raise RuntimeError("Unexpected shape for images: {}".format(shape))

    if clip:  # Set values that were out of range to nan instead of erroring.
        try:  # If the datatype of result is incompatible with nan, set to zero instead.
            result[:, mask] = np.nan
        except:
            result[:, mask] = 0
    else:
        pass

    if plot:
        take_plot(np.reshape(result, (vectors.shape[1], size[1], size[0])))

    if integrate:  # Sum over the integration axis
        return np.sum(result, axis=-1)
    else:  # Reshape the integration axis
        return np.reshape(result, (vectors.shape[1], size[1], size[0]))


def take_plot(images):
    """
    Plots non-integrated results of :meth:`.take()` in a square array of subplots.

    Parameters
    ----------
    images : numpy.ndarray
        Stack of 2D images, usually a :meth:`take()` output.
    """
    (img_count, sy, sx) = np.shape(images)
    M = int(np.ceil(np.sqrt(img_count)))

    plt.figure(figsize=(12, 12))

    sx = sx / 2.0 - 0.5
    sy = sy / 2.0 - 0.5
    extent = (-sx, sx, -sy, sy)

    for x in range(img_count):
        ax = plt.subplot(M, M, x + 1)

        ax.imshow(images[x, :, :], extent=extent)
        ax.axes.xaxis.set_visible(False)
        ax.axes.yaxis.set_visible(False)

    plt.show()


def image_moment(images, moment=(1, 0), centers=(0, 0), normalize=True, nansum=False):
    r"""
    Computes the given `moment <https://en.wikipedia.org/wiki/Moment_(mathematics)>`_
    :math:`M_{m_xm_y}` for a stack of images.
    This involves integrating each image against polynomial trial functions:

    .. math:: M_{m_xm_y} = \frac{   \int_{-w_x/2}^{+w_x/2} dx \, (x-c_x)^{m_x}
                                    \int_{-w_y/2}^{+w_y/2} dy \, (y-c_y)^{m_y}
                                    P(x+x_0, y+y_0)
                                }{  \int_{-w_x/2}^{+w_x/2} dx \,
                                    \int_{-w_y/2}^{+w_y/2} dy \,
                                    P(x, y)},

    where :math:`P(x, y)` is a given 2D image, :math:`(x_0, y_0)` is the center of a
    window of size :math:`w_x \times w_y`, and :math:`(c_x, c_y)` is a shift in the
    center of the trial functions.

    Warning
    ~~~~~~~
    This function does not check if the images in ``images`` are non-negative, or correct
    for this. Negative values may produce unusual results.

    Warning
    ~~~~~~~
    Higher order even moments (e.g. 2) will potentially yield unexpected results if
    the images are not background-subtracted. For instance, a calculation on an image
    with large background will yield the moment of the window, rather than say anything
    about the image.

    Parameters
    ----------
    images : numpy.ndarray
        A matrix in the style of the output of :meth:`take()`, with shape ``(image_count, h, w)``, where
        ``(h, w)`` is the width and height of the 2D images and :math:`image_count` is the number of
        images. A single image is interpreted correctly as ``(1, h, w)`` even if
        ``(h, w)`` is passed.
    moment : (int, int)
        The moments in the :math:`x` and :math:`y` directions: :math:`(m_x, m_y)`. For instance,

        - :math:`M_{m_xm_y} = M_{10}` corresponds to the :math:`x` moment or
          the position in the :math:`x` dimension.
        - :math:`M_{m_xm_y} = M_{11}` corresponds to :math:`xy` shear.
        - :math:`M_{m_xm_y} = M_{02}` corresponds to the :math:`y^2` moment, or the variance
          (squared width for a Gaussian) in the :math:`y` direction,
          given a zero or zeroed (via ``centers``) :math:`M_{01}` moment.

    centers : tuple or numpy.ndarray
        Perturbations to the center of the trial function, :math:`(c_x, c_y)`.
    normalize : bool
        Whether to normalize ``images``.
        If ``False``, normalization is assumed to have been precomputed.
    nansum : bool
        Whether to use :meth:`numpy.nansum()` in place of :meth:`numpy.sum()`.
        :meth:`numpy.nansum()` treats ``nan`` values as zeros.
        This is useful in the case where ``clip=True`` is passed to :meth:`take()`
        (out of range is set to ``nan``).

    Returns
    -------
    numpy.ndarray
        The moment :math:`M_{m_xm_y}` evaluated for every image. This is of size ``(image_count,)``
        for provided ``images`` data of shape ``(image_count, h, w)``.
    """
    if len(images.shape) == 2:
        images = np.reshape(images, (1, images.shape[0], images.shape[1]))
    (img_count, w_y, w_x) = images.shape

    if len(np.shape(centers)) == 2:
        c_x = np.reshape(centers[0], (img_count, 1, 1))
        c_y = np.reshape(centers[1], (img_count, 1, 1))
    elif len(np.shape(centers)) == 1:
        c_x = centers[0]
        c_y = centers[1]

    edge_x = (
        np.reshape(np.power(np.arange(w_x) - (w_x - 1) / 2.0, moment[0]), (1, 1, w_x))
        - c_x
    )
    edge_y = (
        np.reshape(np.power(np.arange(w_y) - (w_y - 1) / 2.0, moment[1]), (1, w_y, 1))
        - c_y
    )

    if nansum:
        np_sum = np.nansum
    else:
        np_sum = np.sum

    if normalize:
        normalization = np_sum(images, axis=(1, 2), keepdims=False)
        reciprical = np.reciprocal(
            normalization, where=normalization != 0, out=np.zeros(img_count,)
        )
    else:
        reciprical = 1

    if moment[1] == 0:  # x case
        return np_sum(images * edge_x, axis=(1, 2), keepdims=False) * reciprical
    elif moment[0] == 0:  # y case
        return np_sum(images * edge_y, axis=(1, 2), keepdims=False) * reciprical
    elif moment[1] != 0 and moment[1] != 0:  # Shear case
        return np_sum(images * edge_x * edge_y, axis=(1, 2), keepdims=False) * reciprical
    else:  # 0,0 (norm) case
        if normalize:
            return np.ones((img_count,))
        else:
            return np_sum(images, axis=(1, 2), keepdims=False)


def image_normalization(images, nansum=False):
    """
    Computes the zeroth order moments, equivalent to spot mass or normalization,
    for a stack of images.

    Parameters
    ----------
    images : numpy.ndarray
        A matrix in the style of the output of :meth:`take()`, with shape ``(image_count, h, w)``, where
        ``(h, w)`` is the width and height of the 2D images and :math:`image_count` is the number of
        images. A single image is interpreted correctly as ``(1, h, w)`` even if
        ``(h, w)`` is passed.
    nansum : bool
        Whether to use :meth:`numpy.nansum()` in place of :meth:`numpy.sum()`.

    Returns
    -------
    numpy.ndarray
        The normalization factor :math:`M_{11}` in an array of shape ``(image_count,)``.
    """
    return image_moment(images, (0, 0), normalize=False, nansum=nansum)


def image_normalize(images, nansum=False):
    """
    Normalizes of a stack of images via the the zeroth order moments.

    Parameters
    ----------
    images : numpy.ndarray
        A matrix in the style of the output of :meth:`take()`, with shape ``(image_count, h, w)``, where
        ``(h, w)`` is the width and height of the 2D images and :math:`image_count` is the number of
        images. A single image is interpreted correctly as ``(1, h, w)`` even if
        ``(h, w)`` is passed.

    Returns
    -------
    images_normalized : numpy.ndarray
        A copy of ``images``, with each image normalized.
    """
    img_count = images.shape[0]
    normalization = image_normalization(images, nansum=nansum)
    reciprical = np.reciprocal(
        normalization, where=normalization != 0, out=np.zeros(img_count,)
    )
    return images * np.reshape(reciprical, (img_count, 1, 1))


def image_positions(images, normalize=True, nansum=False):
    """
    Computes the two first order moments, equivalent to spot position, for a stack of images.
    Specifically, returns :math:`M_{10}` and :math:`M_{01}`.

    Parameters
    ----------
    images : numpy.ndarray
        A matrix in the style of the output of :meth:`take()`, with shape ``(image_count, h, w)``, where
        ``(h, w)`` is the width and height of the 2D images and :math:`image_count` is the number of
        images. A single image is interpreted correctly as ``(1, h, w)`` even if
        ``(h, w)`` is passed.
    normalize : bool
        Whether to normalize ``images``.
        If ``False``, normalization is assumed to have been precomputed.
    nansum : bool
        Whether to use :meth:`numpy.nansum()` in place of :meth:`numpy.sum()`.

    Returns
    -------
    numpy.ndarray
        Stack of :math:`M_{10}`, :math:`M_{01}`.
    """
    if normalize:
        images = image_normalize(images)

    return np.vstack(
        (
            image_moment(images, (1, 0), normalize=False, nansum=nansum),
            image_moment(images, (0, 1), normalize=False, nansum=nansum),
        )
    )


def image_variances(images, centers=None, normalize=True, nansum=False):
    r"""
    Computes the three second order central moments, equivalent to variance, for a stack
    of images.
    Specifically, this function returns a stack of the moments :math:`M_{20}` and
    :math:`M_{02}`, along with :math:`M_{11}`, which are the variance in the :math:`x`
    and :math:`y` directions, along with the so-called shear variance.
    Recall that variance defined as

    .. math:: (\Delta x)^2 = \left<(x - \left<x\right>)^2\right>.

    This equation is made central by subtraction of :math:`\left<x\right>`.
    The user can of course use :meth:`take_moment` directly to access the
    non-central moments; this function is a helper to access useful quantities
    for analysis of spot size and skewness.

    Parameters
    ----------
    images : numpy.ndarray
        A matrix in the style of the output of :meth:`take()`, with shape ``(image_count, h, w)``, where
        ``(h, w)`` is the width and height of the 2D images and :math:`image_count` is the number of
        images. A single image is interpreted correctly as ``(1, h, w)`` even if
        ``(h, w)`` is passed.
    centers : numpy.ndarray OR None
        If the user has already computed :math:`\left<x\right>`, for example via
        :meth:`image_positions()`, then this can be passed though ``centers``. The default
        None computes ``centers`` internally.
    normalize : bool
        Whether to normalize ``images``.
        If ``False``, normalization is assumed to have been precomputed.
    nansum : bool
        Whether to use :meth:`numpy.nansum()` in place of :meth:`numpy.sum()`.

    Returns
    -------
    numpy.ndarray
        Stack of :math:`M_{20}`, :math:`M_{02}`, and :math:`M_{11}`. Shape ``(3, image_count)``.
    """
    if normalize:
        images = image_normalize(images)

    if centers is None:
        centers = image_positions(images, normalize=False, nansum=nansum)

    m20 = image_moment(images, (2, 0), centers=centers, normalize=False, nansum=nansum)
    m11 = image_moment(images, (1, 1), centers=centers, normalize=False, nansum=nansum)
    m02 = image_moment(images, (0, 2), centers=centers, normalize=False, nansum=nansum)

    return np.vstack((m20, m02, m11))


def image_ellipticity(variances):
    r"""
    Given the output of :meth:`image_variances()`,
    return a measure of spot ellipticity for each moment triplet.
    The output of :meth:`image_variances()` contains the moments :math:`M_{20}`,
    :math:`M_{02}`, and :math:`M_{11}`. These terms make up a :math:`2 \times 2` matrix,
    which is equivalent to a rotated elliptical scaling according to the eigenvalues
    :math:`\lambda_+` and :math:`\lambda_-` and some rotation matrix :math:`R(\phi)`.

    .. math::   \begin{bmatrix}
                    M_{20} & M_{11} \\
                    M_{11} & M_{02} \\
                \end{bmatrix}
                =
                R(-\phi)
                \begin{bmatrix}
                    \lambda_+ & 0 \\
                    0 & \lambda_- \\
                \end{bmatrix}
                R(\phi).

    We use this knowledge, along with tricks for eigenvalue calculations on
    :math:`2 \times 2` matrices, to build up a metric for ellipticity:

    .. math:: \mathcal{E} = 1 - \frac{\lambda_-}{\lambda_+}.

    Notice that

    - when :math:`\lambda_+ = \lambda_-` (isotropic scaling), the metric is zero and
    - when :math:`\lambda_- = 0` (flattened to a line), the metric is unity.

    Parameters
    ----------
    variances : numpy.ndarray
        The output of :meth:`image_variances()`. Shape ``(3, image_count)``.

    Returns
    -------
    numpy.ndarray
        Array of ellipticities for the given moments. Shape ``(image_count,)``.
    """
    m20 = variances[0, :]
    m02 = variances[1, :]
    m11 = variances[2, :]

    # We can use a trick for eigenvalue calculations of 2x2 matrices to avoid
    # more complicated calculations.
    half_trace = (m20 + m02) / 2
    determinant = m20 * m20 - m11 * m11

    eig_half_difference = np.sqrt(np.square(half_trace) - determinant)

    eig_plus = half_trace + eig_half_difference
    eig_minus = half_trace - eig_half_difference

    return 1 - (eig_minus / eig_plus)


def image_ellipticity_angle(variances):
    r"""
    Given the output of :meth:`image_variances()`,
    return the rotation angle of the scaled basis for each moment triplet.
    This is the angle between the :math:`x` axis and the
    major axis (large eigenvalue axis).

    Parameters
    ----------
    moment2 : numpy.ndarray
        The output of :meth:`image_variances()`. Shape ``(3, image_count)``.

    Returns
    -------
    numpy.ndarray
        Array of angles for the given moments.
        For highly circular spots, this angle is not meaningful, and dominated by
        experimental noise.
        For perfectly circular spots, zero is returned.
        Shape ``(image_count,)``.
    """
    m20 = variances[0, :]
    m02 = variances[1, :]
    m11 = variances[2, :]

    # Some quick math (see image_variances_circularity).
    half_trace = (m20 + m02) / 2
    determinant = m20 * m20 - m11 * m11

    eig_plus = half_trace + np.sqrt(np.square(half_trace) - determinant)

    # We know that M * v = lambda * v. This yields a system of equations:
    #   m20 * x + m11 * y = lambda * x
    #   m11 * x + m02 * y = lambda * y
    # We're trying to solve for angle, which is just atan(x/y). We can solve for x/y:
    #   m11 * x = (lambda - m02) * y        ==>         x/y = (lambda - m02) / m11
    return np.arctan2(eig_plus - m02, m11, where=m11 != 0, out=np.zeros_like(m11))


def image_fit(images, function=gaussian2d, guess=None, plot=False):
    """
    Fit each image in a stack of images to a 2D ``function``.

    Parameters
    ----------
    images : numpy.ndarray (image_count, height, width)
        An image or array of images to fit. A single image is interpreted correctly as
        ``(1, h, w)`` even if ``(h, w)`` is passed.
    function : lambda ((float, float), ... ) -> float
        Some fitfunction which accepts ``(x,y)`` coordinates as first argument.
        Defaults to :meth:`~slmsuite.misc.fitfunctions.gaussian2d()`.
    guess : None OR numpy.ndarray (parameter_count, image_count)
        - If ``guess`` is ``None``, will construct a guess based on the ``function`` passed.
          Functions for which guesses are implemented include:
          - :meth:`~~slmsuite.misc.fitfunctions.gaussian2d()`
        - If ``guess`` is ``None`` and ``function`` does not have a guess
          implemented, no guess will be provided to the optimizer.
        - If ``guess`` is a ``numpy.ndarray``, a slice of the array will be provided
          to the optimizer as a guess for the fit parameters for each image.
    plot : bool
        Whether to create a plot for each fit.
    show : bool
        Whether or not to call :meth:`matplotlib.pyplot.show` after generating
        the plot.

    Returns
    -------
    numpy.ndarray (``result_count``, ``image_count``)
        A matrix with the fit results. The first row
        contains the rsquared quality of each fit.
        The values in the remaining rows correspond to the parameters
        for the supplied fit function.
        Failed fits have an rsquared of ``numpy.nan`` and parameters
        are set to the provided or constructed guess or ``numpy.nan``
        if no guess was provided or constructed.

    Raises
    ------
        NotImplementedError if the provided ``function`` does not have a guess implemented.
    """
    # Setup.
    (image_count, w_y, w_x) = images.shape
    img_shape = (w_y, w_x)

    edge_x = np.reshape(np.arange(w_x) - (w_x - 1) / 2.0, (1, 1, w_x))
    edge_y = np.reshape(np.arange(w_y) - (w_y - 1) / 2.0, (1, w_y, 1))
    grid_x, grid_y = np.meshgrid(edge_x, edge_y)
    grid_xy = (grid_x.ravel(), grid_y.ravel())

    # Number of fit parameters the function accepts.
    param_count =  function.__code__.co_argcount - 1

    # Number of parameters to return.
    result_count = param_count + 1
    result = np.full((result_count, image_count), np.nan)

    # Construct guesses.
    if guess is None:
        if function is gaussian2d:
            images_normalized = image_normalize(images)
            centers = image_positions(images_normalized, normalize=False)
            variances = image_variances(images_normalized, centers=centers, normalize=False)
            maxs = np.amax(images, axis=(1, 2))
            mins = np.amin(images, axis=(1, 2))

            guess = np.vstack((
                centers,
                maxs - mins,
                mins,
                np.sqrt(variances[0:2, :]),
                variances[2, :]
            ))
            

    for img_idx in range(image_count):
        img = images[img_idx, :, :].ravel()
    
        # Get guess.
        p0 = guess[:, img_idx] if guess is not None else None

        # Attempt fit.
        fit_succeeded = True
        popt = None

        try:
            popt, _ = curve_fit(function, grid_xy, img, ftol=1e-5, p0=p0,)
        except RuntimeError:    # The fit failed if scipy says so.
            fit_succeeded = False
        else:                   # The fit failed if any of the parameters aren't finite.
            if np.any(np.logical_not(np.isfinite(popt))):
                fit_succeeded = False

        if fit_succeeded:   # Calculate r2.
            ss_res = np.sum(np.square(img - function(grid_xy, *popt)))
            ss_tot = np.sum(np.square(img - np.mean(img)))
            r2 = 1 - (ss_res / ss_tot)
        else:               # r2 is nan and the fit parameters are the guess or nan.
            popt = p0 if p0 is not None else np.full(param_count, np.nan)
            r2 = np.nan

        result[0, img_idx] = r2
        result[1:, img_idx] = popt

        # Plot.
        if plot:
            fig, axs = plt.subplots(1, 3, figsize=(3 * 6.4, 4.8))
            fig.suptitle("Image {}".format(img_idx))
            
            ax0, ax1, ax2 = axs

            ax0.imshow(np.reshape(img, img_shape))
            ax0.set_title("Data")

            if p0 is not None:
                ax1.imshow(np.reshape(function(grid_xy, *p0), img_shape))
                ax1.set_title("Guess")

            ax2.imshow(np.reshape(function(grid_xy, *popt), img_shape))
            ax2.set_title("Result")

            plt.show()

    return result


def blob_detect(img, plot=False, title="", filter=None, **kwargs):
    """
    Detect blobs in an image.

    Wraps :class:`cv2.SimpleBlobDetector` [1]_. See also [2]_.
    Default parameters are optimized for bright spot detection on dark background,
    but can be changed with ``**kwargs``.

    Parameters
    ----------
    img : numpy.ndarray
        The image to perform blob detection on.
    filter : {"dist_to_center", "max_amp"} OR None
        One of ``dist_to_center`` or ``max_amp``.
    title : str
        Plot title.
    plot : bool
        Whether to show a debug plot.
    kwargs
       Extra arguments for :class:`cv2.SimpleBlobDetector`.

    Returns
    -------
    blobs : ndarray
        List of blobs found by  ``detector``.
    detector : :class:`cv2.SimpleBlobDetector`
        A blob detector with customized parameters.

    References
    ~~~~~~~~~~
    .. [1] https://docs.opencv.org/3.4/d8/da7/structcv_1_1SimpleBlobDetector_1_1Params.html
    .. [2] https://learnopencv.com/blob-detection-using-opencv-python-c/
    """
    cv2img = _make_8bit(np.copy(img))
    params = cv2.SimpleBlobDetector_Params()

    # Configure default parameters
    params.blobColor = 255
    params.minThreshold = 10
    params.maxThreshold = 255
    params.thresholdStep = 10
    # params.minArea = 0
    params.filterByArea = False  # Can be changed to compute rel to diffraction limit
    params.filterByCircularity = False
    params.filterByConvexity = False
    params.filterByInertia = False

    # Load in custom configuration
    for key, val in kwargs.items():
        setattr(params, key, val)

    # Create the detector and detect blobs
    detector = cv2.SimpleBlobDetector_create(params)
    blobs = detector.detect(cv2img)

    if len(blobs) == 0:
        blurred = cv2.GaussianBlur(cv2img, (3, 3), 0)

        plt.imshow(blurred)
        plt.colorbar()
        plt.title("gaussian blurred")
        plt.show()

        blobs = detector.detect(blurred)
        if len(blobs) == 0:
            raise Exception("No blobs found!")

        print([blob.size for blob in blobs])

    # Downselect blobs if desired by kwargs:
    if filter == "dist_to_center":
        dist_to_center = [
            np.linalg.norm(np.array(blob.pt) - np.array(img.shape[::-1]) / 2)
            for blob in blobs
        ]
        blobs = [blobs[np.argmin(dist_to_center)]]
    elif filter == "max_amp":
        bin_size = int(np.mean([blob.size for blob in blobs]))
        for i, blob in enumerate(blobs):
            # Try fails when blob is on edge of camera.
            try:
                blobs[i].response = float(
                    cv2img[
                        np.ix_(
                            int(blob.pt[1]) + np.arange(-bin_size, bin_size),
                            int(blob.pt[0]) + np.arange(-bin_size, bin_size),
                        )
                    ].sum()
                )
            except Exception:
                blobs[i].response = float(0)
        blobs = [blobs[np.argmax([blob.response for blob in blobs])]]

    if plot:
        for blob in blobs:
            cv2.circle(
                cv2img,
                (int(blob.pt[0]), int(blob.pt[1])),
                int(blob.size * 4),
                (255, 0, 0),
                5,
            )
        plt.figure(dpi=300)
        plt.imshow(cv2img)
        plt.title(title)
        plt.show()

    return blobs, detector


def blob_array_detect(img, size, orientation=None, orientation_check=True, plot=False):
    r"""
    Detect an array of spots and return the orientation as an affine transformation.
    Primarily used for calibration.

    For a rectangular array of spots imaged in ``img``,
    find the variables :math:`\vec{M}` and :math:`\vec{b}` for the  affine transformation

    .. math:: \vec{y} = M \cdot \vec{x} + \vec{b}

    which converts spot indices :math:`\vec{x}` into camera pixel indices :math:`\vec{y}`.

    Parameters
    ----------
    img : numpy.ndarray
        The image in question.
    size : (int, int) OR int
        The size of the rectangular array in number of spots ``(Nx, Ny)``.
        If a single ``int`` size is given, then assume ``(N, N)``.
    orientation : dict or None
        Guess array orientation (same format as the returned) from previous known results.
        If None (the default), orientation is estimated from looking for peaks in the
        Fourier transform of the image.
    orientation_check : bool
        If enabled, looks for two missing spots at one corner as a parity check on rotation.
        Used by :meth:`~slmsuite.hardware.cameraslms.FourierSLM.fourier_calibrate()`.
        See :meth:`~slmsuite.hardware.cameraslms.FourierSLM.make_rectangular_array()`.
    plot : bool
        Whether or not to plot debug plots. Default is ``False``.

    Returns
    --------
    dict
        Orientation dictionary with the following keys, corresponding to
        the affine transformation:

         - ``"M"`` : 2x2 ``numpy.ndarray``
         - ``"b"`` : 2x1 ``numpy.ndarray``.
    """
    cv2img = _make_8bit(img)
    start_orientation = orientation

    if orientation is None:
        # FFT to find array pitch and orientation
        # Take the largest dimension rounded up to nearest power of 2.
        fftsize = int(2 ** np.ceil(np.log2(np.max(np.shape(img)))))
        dft = np.fft.fftshift(np.fft.fft2(cv2img, s=[fftsize, fftsize]))
        fft_blur_size = (
            int(2 * np.ceil(fftsize / 1000)) + 1
        )  # Future: Make not arbitrary.
        # dft_amp = np.abs(dft) # cv2.GaussianBlur(np.abs(dft), (fft_blur_size, fft_blur_size), 0)
        dft_amp = cv2.GaussianBlur(np.abs(dft), (fft_blur_size, fft_blur_size), 0)

        # Need copy for some reason:
        # https://github.com/opencv/opencv/issues/18120
        minThreshold = 50
        thresholdStep = 10
        blobs, _ = blob_detect(
            dft_amp.copy(),
            plot=False,
            minThreshold=minThreshold,
            thresholdStep=thresholdStep,
        )
        blobs = np.array(blobs)

        # Debugging plots
        if len(blobs) < 5:
            if plot:
                blobs, _ = blob_detect(
                    dft_amp.copy(),
                    plot=plot,
                    minThreshold=minThreshold,
                    thresholdStep=thresholdStep,
                )

                plt.imshow(cv2img)
                plt.show()

                plt_img = _make_8bit(dft_amp.copy())

                plt.imshow(plt_img)
                plt.title("DFT peaks for scale/rotation")
                plt.colorbar()
                plt.xticks([])
                plt.yticks([])
                plt.show()

            raise RuntimeError(
                "Not enough spots found in FT; expected five. Check exposure time!"
            )

        # Future: improve this part of the algorithm. It sometimes makes mistakes.

        # 2.1) Get the max point (DTF center) and its next four neighbors.
        blob_dist = np.zeros(len(blobs))
        k = np.zeros((len(blobs), 2))
        for i, blob in enumerate(blobs):
            k[i, 0] = -1 / 2 + blob.pt[0] / dft_amp.shape[1]
            k[i, 1] = -1 / 2 + blob.pt[1] / dft_amp.shape[0]
            blob_dist[i] = np.linalg.norm(
                np.array([k[i, 0], k[i, 1]])
            )  # Assumes max at center

        sort_ind = np.argsort(blob_dist)[:5]
        blobs = blobs[sort_ind]
        blob_dist = blob_dist[sort_ind]
        k = k[sort_ind]

        # 2.2) Calculate array metrics
        left = np.argmin([k[:, 0]])  # Smallest x
        right = np.argmax([k[:, 0]])  # Largest x
        bottom = np.argmin([k[:, 1]])  # Smallest y
        top = np.argmax([k[:, 1]])  # Largest y

        # 2.3) Calculate the vectors in the imaging domain
        x = 2 * (k[right, :] - k[left, :]) / (blob_dist[right] + blob_dist[left]) ** 2
        y = 2 * (k[top, :] - k[bottom, :]) / (blob_dist[top] + blob_dist[bottom]) ** 2

        M = np.array([[x[0], y[0]], [x[1], y[1]]])
    else:
        M = orientation["M"]

    # 3) Make the array kernel for convolutional detection of the array center.
    # Make lists that we will use to make the kernel: the array...
    x_list = np.arange(-(size[0] - 1) / 2.0, (size[0] + 1) / 2.0)
    y_list = np.arange(-(size[1] - 1) / 2.0, (size[1] + 1) / 2.0)

    x_centergrid, y_centergrid = np.meshgrid(x_list, y_list)
    centers = np.vstack((x_centergrid.ravel(), y_centergrid.ravel()))

    # ...and the array padded by one.
    pad = 1
    p = int(pad * 2)

    x_list_larger = np.arange(-(size[0] + p - 1) / 2.0, (size[0] + p + 1) / 2.0)
    y_list_larger = np.arange(-(size[1] + p - 1) / 2.0, (size[1] + p + 1) / 2.0)

    x_centergrid_larger, y_centergrid_larger = np.meshgrid(x_list_larger, y_list_larger)
    centers_larger = np.vstack(
        (x_centergrid_larger.ravel(), y_centergrid_larger.ravel())
    )

    # If we're not sure about how things are flipped, consider alternatives
    if size[0] != size[1] and orientation is None:
        M_alternative = np.array([[M[0, 1], M[0, 0]], [M[1, 1], M[1, 0]]])
        M_options = [M, M_alternative]
    else:
        M_options = [M]

    results = []

    # Iterate through these alternatives
    for M_trial in M_options:
        # Find the position of the centers for this trial matrix.
        rotated_centers = np.matmul(M_trial, centers)
        rotated_centers_larger = np.matmul(M_trial, centers_larger)

        # Make the kernel
        max_pitch = int(
            np.amax([np.linalg.norm(M_trial[:, 0]), np.linalg.norm(M_trial[:, 1])])
        )

        mask = np.zeros(
            (
                int(
                    np.amax(rotated_centers_larger[1, :])
                    - np.amin(rotated_centers_larger[1, :])
                    + max_pitch
                ),
                int(
                    np.amax(rotated_centers_larger[0, :])
                    - np.amin(rotated_centers_larger[0, :])
                    + max_pitch
                ),
            )
        )

        rotated_centers += np.flip(mask.shape)[:, np.newaxis] / 2
        rotated_centers_larger += np.flip(mask.shape)[:, np.newaxis] / 2

        # Pixels to use for the kernel.
        x_array = rotated_centers[0, :].astype(np.int)
        y_array = rotated_centers[1, :].astype(np.int)

        x_larger = rotated_centers_larger[0, :].astype(np.int)
        y_larger = rotated_centers_larger[1, :].astype(np.int)

        # Make a mask with negative power at the border, positive
        # at the array, with integrated intensity of 0.
        area = size[0] * size[1]
        perimeter = 2 * (size[0] + size[1]) + 4

        mask[y_larger, x_larger] = -area
        mask[y_array, x_array] = perimeter

        mask = _make_8bit(mask)

        # 4) Do the autocorrelation
        try:
            res = cv2.matchTemplate(cv2img, mask, cv2.TM_CCOEFF)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
        except:
            max_val = 0
            max_loc = [0, 0]

        b_fixed = (
            np.array(max_loc)[:, np.newaxis] + np.flip(mask.shape)[:, np.newaxis] / 2
        )

        # Parity check
        if orientation is None and orientation_check:
            try:
                cam_array_ind = np.ix_(
                    max_loc[1] + np.arange(mask.shape[0]),
                    max_loc[0] + np.arange(mask.shape[1]),
                )
                match = cv2img[cam_array_ind]

                wmask = 0.1
                w = np.max([1, int(wmask * max_pitch)])
                edge = np.arange(-w, w + 1)

                integration_x, integration_y = np.meshgrid(edge, edge)

                rotated_integration_x = np.add(
                    integration_x.ravel()[:, np.newaxis].T,
                    rotated_centers[:][0][:, np.newaxis],
                ).astype(np.int)
                rotated_integration_y = np.add(
                    integration_y.ravel()[:, np.newaxis].T,
                    rotated_centers[:][1][:, np.newaxis],
                ).astype(np.int)

                spotpowers = np.reshape(
                    np.sum(match[rotated_integration_y, rotated_integration_x], 1),
                    np.flip(size),
                )

                # Find the two dimmest pixels.
                spotbooleans = spotpowers <= np.sort(spotpowers.ravel())[1]

                assert np.sum(spotbooleans) == 2

                # Find whether the corners are dimmest.
                corners = spotbooleans[[-1, -1, 0, 0], [-1, 0, 0, -1]]

                assert np.sum(corners) == 1

                # We want a dim corner at -1, -1.
                rotation_parity = np.where(corners)[0][0]
                spotbooleans_rotated = np.rot90(spotbooleans, rotation_parity)

                theta = rotation_parity * np.pi / 2
                c = np.cos(theta)
                s = np.sin(theta)
                rotation = np.array([[c, -s], [s, c]])

                # Look for the second missing spot.
                flip_parity = int(spotbooleans_rotated[-1, -2]) - int(
                    spotbooleans_rotated[-2, -1]
                )

                assert abs(flip_parity) == 1

                if flip_parity == 1:
                    flip = np.array([[1, 0], [0, 1]])
                else:
                    flip = np.array([[0, 1], [1, 0]])

                M_fixed = np.matmul(M_trial, np.matmul(rotation, flip))
                parity_success = True
            except Exception as e:
                print(e)

                M_fixed = M_trial
                parity_success = False
        else:
            M_fixed = M_trial
            parity_success = True

        results.append((max_val, b_fixed, M_fixed, parity_success))

    if len(results) == 1:
        index = 0
    else:
        # Default to max_val if the parity check results in the same thing.
        if results[0][3] == results[1][3]:
            index = int(results[1][0] > results[0][0])
        else:
            # Index is the one that satisfied the parity check
            index = int(results[1][3])

    orientation = {"M": results[index][2], "b": results[index][1]}

    if plot:
        array_center = orientation["b"]
        true_centers = np.matmul(orientation["M"], centers) + orientation["b"]

        if start_orientation is None:
            _, axs = plt.subplots(1, 2, constrained_layout=True, figsize=(12, 6))

            plt_img = _make_8bit(dft_amp.copy())

            # Determine the bounds of the zoom region, padded by zoom_pad
            zoom_pad = 50

            x = np.array([blob.pt[0] for blob in blobs])
            xl = [
                np.clip(np.amin(x) - zoom_pad, 0, dft_amp.shape[1]),
                np.clip(np.amax(x) + zoom_pad, 0, dft_amp.shape[1]),
            ]

            y = np.array([blob.pt[1] for blob in blobs])
            yl = [
                np.clip(np.amin(y) - zoom_pad, 0, dft_amp.shape[0]),
                np.clip(np.amax(y) + zoom_pad, 0, dft_amp.shape[0]),
            ]

            axs[1].imshow(plt_img)
            axs[1].set_title("DFT Result - Zoom")
            axs[1].set_xticks([])
            axs[1].set_yticks([])
            axs[1].set_xlim(xl)
            axs[1].set_ylim(np.flip(yl))
            axs[1].scatter(
                x,
                y,
                facecolors="none",
                edgecolors="r",
                marker="o",
                s=1000,
                linewidths=1,
            )

            # Plot the unzoomed figure
            axs[0].imshow(plt_img)

            # Plot a red rectangle to show the extents of the zoom region
            rect = plt.Rectangle(
                [xl[0], yl[0]], np.diff(xl), np.diff(yl), ec="r", fc="none"
            )
            axs[0].add_patch(rect)
            axs[0].set_title("DFT Result - Full")
            axs[0].set_xticks([])
            axs[0].set_yticks([])

            plt.show()

    def hone():
        guess_positions = np.matmul(orientation["M"], centers) + orientation["b"]

        # Odd helper parameters.
        psf = 2 * int(np.floor(np.amin(np.amax(orientation["M"], axis=0))) / 2) + 1
        blur = 2 * int(psf / 16) + 1

        regions = take(
            img, guess_positions, psf, centered=True, integrate=False, clip=True
        )

        # TODO: Update with take and take moments.

        # Filter the images, but not the stack.
        sp_gaussian_filter1d(regions, blur, axis=1, output=regions)
        sp_gaussian_filter1d(regions, blur, axis=2, output=regions)

        # Future: fit gaussians instead of taking the (integer) max point for floating accuracy.
        shift_x = (
            np.argmax(np.amax(regions, axis=1, keepdims=True), axis=2) - (psf - 1) / 2
        )
        shift_y = (
            np.argmax(np.amax(regions, axis=2, keepdims=True), axis=1) - (psf - 1) / 2
        )
        shift_error = np.sqrt(np.square(shift_x) + np.square(shift_y))

        thresh = np.mean(shift_error)

        shift_x[shift_error > thresh] = np.nan
        shift_y[shift_error > thresh] = np.nan

        if False:
            fig, axs = plt.subplots(2, 2, figsize=(12, 12))
            im = axs[0, 0].imshow(shift_x.reshape(np.flip(size)))
            plt.colorbar(im, ax=axs[0, 0])
            im = axs[1, 0].imshow(shift_y.reshape(np.flip(size)))
            plt.colorbar(im, ax=axs[1, 0])

            axs[0, 1].hist(shift_x.ravel(), bins=30)
            axs[1, 1].hist(shift_y.ravel(), bins=30)

            plt.show()

        orientation["b"] += format_2vectors([np.nanmean(shift_x), np.nanmean(shift_y)])

    hone()
    hone()

    if plot:
        array_center = orientation["b"]
        true_centers = np.matmul(orientation["M"], centers) + orientation["b"]

        showmatch = False

        _, axs = plt.subplots(
            1, 2 + showmatch, constrained_layout=True, figsize=(12, 6)
        )

        # Determine the bounds of the zoom region, padded by 50
        x = true_centers[0, :]
        xl = [
            np.clip(np.amin(x) - max_pitch, 0, img.shape[1]),
            np.clip(np.amax(x) + max_pitch, 0, img.shape[1]),
        ]
        y = true_centers[1, :]
        yl = [
            np.clip(np.amin(y) - max_pitch, 0, img.shape[0]),
            np.clip(np.amax(y) + max_pitch, 0, img.shape[0]),
        ]

        axs[1].imshow(img)
        axs[1].scatter(
            x, y, facecolors="none", edgecolors="r", marker="o", s=80, linewidths=0.5
        )

        for i, ctr in enumerate(true_centers.T):
            if i < 2 or i > len(true_centers.T) - 3:
                axs[1].annotate(i, (ctr[0] + 4, ctr[1] - 4), c="r", size="x-small")

        axs[1].scatter(array_center[0], array_center[1], c="r", marker="x", s=10)
        axs[1].set_title("Result - Zoom")
        axs[1].set_xlim(xl)
        axs[1].set_ylim(np.flip(yl))

        axs[0].imshow(cv2img)
        axs[0].scatter(array_center[0], array_center[1], c="r", marker="x", s=10)

        # Plot a red rectangle to show the extents of the zoom region
        rect = plt.Rectangle(
            [xl[0], yl[0]], np.diff(xl), np.diff(yl), ec="r", fc="none"
        )
        axs[0].add_patch(rect)
        axs[0].set_title("Result - Full")

        if showmatch:
            axs[2].imshow(match)
            axs[2].set_title("Result - Match")

        plt.show()

    return orientation


def _make_8bit(img):
    """
    Convert an image to ``numpy.uint8``, scaling to the limits.

    This function is useful to convert float or larger bitdepth images to
    8-bit, which cv2 accepts and can speedily process.

    Parameters
    ----------
    img : numpy.ndarray
        The image in question.

    Returns
    -------
    ndarray
        img as an 8-bit image.
    """
    img = img.astype(np.float)

    img -= np.amin(img)
    img = img / np.amax(img) * (2 ** 8 - 1)

    return img.astype(np.uint8)


def get_orientation_transformation(rot="0", fliplr=False, flipud=False):
    """
    Compile a transformation lambda from simple rotates and flips.

    Useful to turn an image to an orientation which is user-friendly.
    Used by :class:`~slmsuite.hardware.cameras.camera.Camera` and subclasses.

    Parameters
    ----------
    rot : str OR int
        Rotates returned image by the corresponding degrees in ``["90", "180", "270"]``
        or :meth:`numpy.rot90` code in ``[1, 2, 3]``. Defaults to no rotation otherwise.
    fliplr : bool
        Flips returned image left right.
    flipud : bool
        Flips returned image up down.

    Returns
    -------
    function (array_like) -> numpy.ndarray
        Compiled image transformation.
    """
    transforms = list()

    if fliplr == True:
        transforms.append(np.fliplr)
    if flipud == True:
        transforms.append(np.flipud)

    if rot == "90" or rot == 1:
        transforms.append(lambda img: np.rot90(img, 1))
    elif rot == "180" or rot == 2:
        transforms.append(lambda img: np.rot90(img, 2))
    elif rot == "270" or rot == 3:
        transforms.append(lambda img: np.rot90(img, 3))

    return reduce(lambda f, g: lambda x: f(g(x)), transforms, lambda x: x)
