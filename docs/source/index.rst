slmsuite
========

|slmsuite|_ is a Python package for high-precision
spatial light modulator (SLM) control and holography.

.. sidebar:: Hone Your Spots

   |slmsuite|_ enables **spot-specific**
   `Zernike
   <https://slmsuite.readthedocs.io/en/latest/_examples/zernike_holography.html>`_
   aberration correction; capable of optimizing spot imaging
   `across a field of view
   <https://slmsuite.readthedocs.io/en/latest/_examples/multipoint_calibration.html>`_.

   .. image:: https://raw.githubusercontent.com/slmsuite/slmsuite-examples/main/examples/ex-zernike-spots-dark.gif
      :class: only-dark
      :alt:
         Alongside steering spots in three dimensions, this feature enables removal of
         aberration across a wide field of view. Every spot in the field of view
         is sourced along a different optical path, and slmsuite can correct for each
         different aberration experienced.

   .. image:: https://raw.githubusercontent.com/slmsuite/slmsuite-examples/main/examples/ex-zernike-spots.gif
      :class: only-light
      :alt:
         Alongside steering spots in three dimensions, this feature enables removal of
         aberration across a wide field of view. Every spot in the field of view
         is sourced along a different optical path, and slmsuite can correct for each
         different aberration experienced.

   |

.. sidebar:: Enhance Your Holography

   Camera
   `feedback
   <https://slmsuite.readthedocs.io/en/latest/_autosummary/slmsuite.holography.algorithms.FeedbackHologram.html#slmsuite.holography.algorithms.FeedbackHologram>`_
   and phase
   `flattening
   <https://slmsuite.readthedocs.io/en/latest/_autosummary/slmsuite.holography.algorithms.Hologram.html#slmsuite.holography.algorithms.Hologram.reset_phase>`_
   in |slmsuite|_ lead to crisp and accurate experimental
   `holograms
   <https://slmsuite.readthedocs.io/en/latest/_examples/experimental_holography.html>`_,
   even across
   `multiple planes
   <https://slmsuite.readthedocs.io/en/latest/_examples/multiplane_holography.html>`_  of focus, color, or basis.

   .. image:: https://raw.githubusercontent.com/slmsuite/slmsuite-examples/main/examples/ex-slmsuite-3d-dark.gif
      :class: only-dark
      :alt:
         Advanced meta-hologram programming optimizes spot and image objectives simultaneously.

   .. image:: https://raw.githubusercontent.com/slmsuite/slmsuite-examples/main/examples/ex-slmsuite-3d.gif
      :class: only-light
      :alt:
         Advanced meta-hologram programming optimizes spot and image objectives simultaneously.

   |

.. raw:: html

   <p align="center">
   <a href="https://pypi.org/project/slmsuite/"><img alt="PyPi Package" src="https://img.shields.io/badge/pypi-v0.3.0-3776AB.svg"></a>
   <a href="https://github.com/slmsuite/slmsuite/blob/main/LICENSE"><img alt="License: MIT" src="https://img.shields.io/github/license/slmsuite/slmsuite?color=purple"></a>
   <a href="https://github.com/psf/black"><img alt="Code style: black" src="https://img.shields.io/badge/code%20style-black-000000.svg"></a>
   <a href="https://arxiv.org/abs/2505.08777"><img alt="Citation" src="https://img.shields.io/badge/cite-arXiv%3A2505.08777-B31B1B.svg"></a>
   <a href="https://github.com/slmsuite/slmsuite"><img alt="GitHub Repo stars" src="https://img.shields.io/github/stars/slmsuite/slmsuite"></a>
   </p>

Contact us at qp-slm@mit.edu or on
`GitHub <https://github.com/slmsuite/slmsuite>`_
`Issues <https://github.com/slmsuite/slmsuite/issues>`_
or
`Discussions <https://github.com/slmsuite/slmsuite/discussions>`_.

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   introduction
   installation

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   examples
   api
   tips


Citation
--------

|slmsuite|_ is built upon the work of many others. If you used any technique in particular,
be sure to check our documentation for links to relevant papers.
For acknowledgement of the package or unique features such as
aberration-space holography, please use the following citation:

.. code-block:: bibtex

   @misc{
      christen2025slmsuite,
      Author = {Ian Christen and Christopher Panuski and Thomas Propson and Dirk Englund},
      Title = {Full-volume aberration-space holography},
      Year = {2025},
      Eprint = {arXiv:2505.08777},
   }

.. |slmsuite| replace:: :mod:`slmsuite`
.. _slmsuite: https://github.com/slmsuite/slmsuite