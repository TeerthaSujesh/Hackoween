"""CKD-EPI 2021 Creatinine eGFR Equation.

Deterministic implementation of the 2021 CKD-EPI (Chronic Kidney Disease Epidemiology
Collaboration) creatinine equation without race coefficient, per KDIGO 2024 standards.
"""

from typing import Union


def calculate_egfr(scr: float, age: Union[int, float], female: bool = False) -> float:
    """Calculate estimated Glomerular Filtration Rate (eGFR) using CKD-EPI 2021.

    Formula:
        eGFR = 142 * min(Scr/kappa, 1)^alpha * max(Scr/kappa, 1)^(-1.200) * 0.9938^age * (1.012 if female else 1.0)
    where:
        kappa = 0.7 if female else 0.9
        alpha = -0.241 if female else -0.302
        Scr = serum creatinine in mg/dL
        age = age in years

    Args:
        scr: Serum creatinine in mg/dL.
        age: Age in years.
        female: True if biological sex is female, False if male.

    Returns:
        float: Calculated eGFR in mL/min/1.73m2, rounded to 1 decimal place.
    """
    if scr <= 0:
        raise ValueError("Serum creatinine must be strictly positive.")
    if age <= 0:
        raise ValueError("Age must be strictly positive.")

    kappa, alpha = (0.7, -0.241) if female else (0.9, -0.302)
    ratio = scr / kappa

    base_egfr = 142.0 * (min(ratio, 1.0) ** alpha) * (max(ratio, 1.0) ** -1.200) * (0.9938 ** float(age))
    if female:
        base_egfr *= 1.012

    return round(base_egfr, 1)
