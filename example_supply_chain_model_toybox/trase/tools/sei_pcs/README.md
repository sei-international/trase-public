The _Trase SEI-PCS tool_ is a set of Python classes and functions designed to aid the development of _Standardised Spatially Explicit Information on Production to Consumption_ (sSEI-PCS) models.
From the perspective of the person developing the model, the tool:

 1. Helps you **load data** into the model; even if the data recently changed at its source
 1. Runs **quality assurance** on the input data: in particular ensuring that datasets can be fully-joined on common columns
 1. Provides **useful wrapping functions** around Pandas that provides a higher-level abstraction to things we often need to do in SEI-PCS models, such as "consolidation" or "splitting"
 1. **Writes out model results** in a standard, Trase-style results file

For the whole Trase project, the tool:

 1. Sets some standards about how data is loaded and written so that we can all work more efficiently
 1. Ensures that similar models have very similar-looking code, to reduce the cognitive load on the team    
 1. Provides a standard interface to run models so that _anybody_ on the team can run them, even if they didn't originally work on the model

## Guiding Principles

The tool is written with a few guiding principles in mind:

 1. Be _lightweight_ (in the sense of a small amount of code) and _modular_
 1. Set standards _by default_ but don't enforce them, in order to remain flexible to needs
 1. Leverage Pandas 🐼 where possible: do not reinvent existing standards in the data science community 
