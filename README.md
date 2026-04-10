# REQ-TDD:Requirement-Guided Test-Driven Development for Modular Code Generation with Large Language Model

This repository contains the reproducibility package for the **REQ-TDD** project, which aims to automate the generation of code and tests directly from Software Requirements Specifications (SRS) documents. The project leverages Large Language Models (LLMs) to transform high-level requirements into executable MVC (Model-View-Controller) structured code and corresponding test cases, following a Test-Driven Development (TDD) approach. For venue, citation, and PDF, see the associated conference paper.

**PDF:** *(link to paper when available)*

**DOI:** *(e.g., Zenodo or artifact DOI when available)*

## Authors

- **Wasay Mohammed Abdul** — Texas State University, San Marcos, TX, USA — [w_m91@txstate.edu](mailto:w_m91@txstate.edu)
- **Ragib Shahariar Ayon** — Texas State University, San Marcos, TX, USA — [ipd21@txstate.edu](mailto:ipd21@txstate.edu)
- **Shibbir Ahmed** — Texas State University, San Marcos, TX, USA — [shibbir@txstate.edu](mailto:shibbir@txstate.edu)
- **Rodion Podorozhny** — Texas State University, San Marcos, TX, USA — [rp31@txstate.edu](mailto:rp31@txstate.edu)

---

## Index

- [Reproducibility package](#reproducibility-package)
- [Installation and reproducibility instructions](#installation-and-reproducibility-instructions)
- [Repository structure](#repository-structure)
- [How to use](#how-to-use-for-reproducibility)

---

## Reproducibility package

This reproducibility package provides the datasets, prompts, and results used in our experiments.

The REQ-TDD system is designed as a VS Code extension that takes an SRS document as input and performs the following steps:

1. **SRS Parsing:** Extracts functional requirements and use cases from the SRS document.
2. **Contract Generation:** Creates a detailed API contract/specification based on the extracted functionalities.
3. **Test Generation:** Generates comprehensive test cases (e.g., using Pytest for Python) based on the contract.
4. **Code Generation:** Generates MVC-structured code (e.g., Flask for Python) that aims to pass the generated tests.
5. **Feedback Loop:** Iteratively refines the generated code based on test failures until all tests pass.

For more details on the methodology and experimental setup, please refer to the associated conference paper.

---

## Installation and reproducibility instructions

### Environment setup

Follow these steps to clone the repository and inspect or reproduce artifacts.

**1. Clone this repository and move to the directory** (terminal, bash, or PowerShell):

```bash
git clone https://github.com/Wasay-Dev100/Requirement-Guided-Test-Driven-Development-for-Modular-Code-Generation-with-Large-Language-Model.git req-tdd
cd req-tdd
```

**2. View generated outputs and inputs**

- Open the `Results` directory to view the generated code and tests.
- Open the `Datasets` and `Prompts` folders to see the SRS inputs and LLM prompts used for generation.

**3. (Optional) Re-run tests** on a generated project under `Results/` if that folder includes a Python environment (e.g., `requirements.txt`). Use a virtual environment and install dependencies before running `pytest`, consistent with the stack described in the paper.

---

## Repository structure

- `Datasets/`: Contains the original SRS documents (PDFs) used for generating code and tests.
  - `dineout srs.pdf`
  - `Human SRS.pdf`
  - `kinmail srs.pdf`
- `Prompts/`: Contains the LLM prompts used for code and test generation.
  - `CodeGenerator_Prompt.txt`
  - `TestcaseGenerator_Prompt.txt`
- `Results/`: Contains the generated MVC code and test results for each SRS dataset.
  - `dineout_srs_mvc/`: Merged MVC code for the Dineout SRS.
  - `dineout_test_results/`: Test results for the Dineout SRS.
  - `human_srs_mvc/`: Merged MVC code for the Human SRS.
  - `human_srs_test_results/`: Test results for the Human SRS.
  - `kinmail_srs_mvc/`: Merged MVC code for the Kinmail SRS.
  - `kinmail_test_results/`: Test results for the Kinmail SRS.

---

## How to use (for reproducibility)

1. Clone this repository: `git clone https://github.com/Wasay-Dev100/Requirement-Guided-Test-Driven-Development-for-Modular-Code-Generation-with-Large-Language-Model.git req-tdd`
2. Navigate to the `Results` directory to view the generated code and tests.
3. Refer to the `Datasets` and `Prompts` folders to understand the inputs used for generation.

For more details on the methodology and experimental setup, please refer to the associated conference paper.
