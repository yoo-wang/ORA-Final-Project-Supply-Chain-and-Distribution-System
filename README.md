# ORA Final Project : Supply Chain and Distribution System
**Implementation of a Distributionally Robust Optimization Model on IEEE 13-Node System**

## Editors and Advisor
| Identity | Name | Contact Information |
| :--- | :--- | :--- |
| Editor/ Student | **胡銘哲 (Min-Zhe, Hu)** | [Email](mailto:youremail@example.com) |
| Editor/ Student | **王宥惠 (Yu-Hui, Wang)** | [Email](mailto:huihui.162636@gmail.com) |
| Advisor |  **李家岩 (Chia-Yen Lee, Ph.D.)**

## Table of Contents
[1.Background and Motivation](#background-and-motivation)
   * [1.1 Motivation](#motivation)
   * [1.2 Background](#background)
   * [1.3 Problem Definition](#problem-definition)

[2.Methodology](#methodology)

[3.Data Collection and Analysis Result](#data-collection-and-analysis-result)

[4.Conclusion](#conclusion)

[5.References](#references)
  


## 1. Background and Motivation
### 1.1 Motivation
Electricity is extremely critical for everyone in modern society, yet traditional network planning often neglect "worst-case" scenarios, focusing instead on daily load growth or single-point failures. This leaves our systems vulnerable to natural disasters, such as hurricanes and earthquakes, which can cause catastrophic, simultaneous outages. Therefore, our primary goal is to prioritize resilience.

To achieve this, we adopt a progressive implementation strategy. We begin by validating the basic grid topology, then move to simulating known disaster paths. Finally, we incorporate uncertainty regarding disaster types and probabilities. By systematically optimizing line hardening and backup generator allocation, this project aims to ensure the continuity of power systems and minimize economic losses when the grid is tested to its limits.

### 1.2 Background
Modern power distribution systems are inherently vulnerable to natural disasters due to their environmentally exposed infrastructure. Extreme events can damage multiple components simultaneously instead of typical "single-point failure" scenarios.

The core problem is that conventional planning models are insufficient for these high-impact events. Traditional methods focus on meeting load growth or maintaining reliability under "N-1 criteria" (assuming only one component fails at a time), which fail to address the simultaneous, multi-component outages caused by extreme weather.

This creates a critical need for Resilience-Oriented Planning. By proactively hardening lines and allocating backup distributed generators (B-DGs), we can robustify the distribution network. This approach benefits us by enhancing the system's ability to quickly recover from disasters, ensuring the continuity of essential power services when they are needed most.

### 1.3 Problem Definition
This project implements a resilience-oriented optimization model to determine the optimal strategies for line hardening and DG allocation, aiming to minimize the expected load shedding penalties when facing extreme weather events.

## 2. Methodology


## 3. Data Collection and Analysis Result

## 4. Conclusion

## 5. References
Zhang, G., Zhang, F., Zhang, X., Wu, Q., & Meng, K. (2020). A multi-disaster-scenario distributionally robust planning model for enhancing the resilience of distribution systems. International Journal of Electrical Power and Energy Systems, 122, Article 106161. https://doi.org/10.1016/j.ijepes.2020.106161

W. H. Kersting, "Radial distribution test feeders," 2001 IEEE Power Engineering Society Winter Meeting. Conference Proceedings (Cat. No.01CH37194), Columbus, OH, USA, 2001, pp. 908-912 vol.2, doi: 10.1109/PESW.2001.916993. keywords: {Conductors;Load modeling;Distributed computing;System testing;Capacitors;Phase transformers;Impedance;Shunt (electrical);Aluminum;Copper}, https://ieeexplore.ieee.org/document/916993
