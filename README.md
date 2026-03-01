# FR2TDD: Functional Requirements to Test-Driven Development

This repository contains the reproducibility package for the FR2TDD project, which aims to automate the generation of code and tests directly from Software Requirements Specifications (SRS) documents. The project leverages Large Language Models (LLMs) to transform high-level requirements into executable MVC (Model-View-Controller) structured code and corresponding test cases, following a Test-Driven Development (TDD) approach.

## Project Overview

The FR2TDD system is designed as a VS Code extension that takes an SRS document as input and performs the following steps:
1. **SRS Parsing:** Extracts functional requirements and use cases from the SRS document.
2. **Contract Generation:** Creates a detailed API contract/specification based on the extracted functionalities.
3. **Test Generation:** Generates comprehensive test cases (e.g., using Pytest for Python) based on the contract.
4. **Code Generation:** Generates MVC-structured code (e.g., Flask for Python) that aims to pass the generated tests.
5. **Feedback Loop:** Iteratively refines the generated code based on test failures until all tests pass.

This reproducibility package provides the datasets, prompts, and results used in our experiments.

## Repository Structure

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

## How to Use (for reproducibility)

1. Clone this repository:
   `git clone https://github.com/SrstoCode/fr2tdd.git`
2. Navigate to the `Results` directory to view the generated code and tests.
3. Refer to the `Datasets` and `Prompts` folders to understand the inputs used for generation.

For more details on the methodology and experimental setup, please refer to the associated conference paper.
