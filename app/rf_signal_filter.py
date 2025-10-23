#!/usr/bin/env python3
"""
RF Signal Filter - Handles signal fluctuation and noise reduction

This module provides signal smoothing and filtering to handle:
- RF multipath interference
- Rapid RSSI fluctuations
- Antenna orientation effects
- Environmental noise

Uses multiple filtering techniques:
1. Exponential Moving Average (EMA) - Fast response with smoothing
2. Median filtering - Remove outliers/spikes
3. Kalman-lite filtering - Predict and smooth based on recent trends
"""

from collections import deque
from typing import Optional, Dict, Tuple
from statistics import median
import time


class SignalSmoother:
    """
    Exponential Moving Average (EMA) smoother
    
    Fast and simple, good for real-time processing
    Lower alpha = more smoothing (0.1-0.3 recommended)
    Higher alpha = faster response (0.5-0.8)
    """
    
    def __init__(self, alpha: float = 0.3):
        """
        Args:
            alpha: Smoothing factor (0-1). Lower = more smoothing
        """
        self.alpha = alpha
        self.smoothed_value: Optional[float] = None
    
    def update(self, new_value: float) -> float:
        """Update with new RSSI value and return smoothed result"""
        if self.smoothed_value is None:
            self.smoothed_value = new_value
        else:
            self.smoothed_value = self.alpha * new_value + (1 - self.alpha) * self.smoothed_value
        
        return self.smoothed_value
    
    def reset(self):
        """Reset the smoother"""
        self.smoothed_value = None


class MedianFilter:
    """
    Median filter for removing outliers and spikes
    
    Maintains a sliding window of recent values
    Returns median of window (resistant to outliers)
    """
    
    def __init__(self, window_size: int = 5):
        """
        Args:
            window_size: Number of samples to keep (3-7 recommended)
        """
        self.window_size = window_size
        self.window = deque(maxlen=window_size)
    
    def update(self, new_value: float) -> float:
        """Update with new RSSI value and return median"""
        self.window.append(new_value)
        return median(self.window)
    
    def reset(self):
        """Reset the filter"""
        self.window.clear()


class KalmanLiteFilter:
    """
    Simplified Kalman filter for RSSI smoothing
    
    Predicts next value based on recent trend
    Combines prediction with measurement for smooth output
    """
    
    def __init__(self, process_variance: float = 0.5, measurement_variance: float = 2.0):
        """
        Args:
            process_variance: How much we expect signal to change
            measurement_variance: How noisy measurements are
        """
        self.process_variance = process_variance
        self.measurement_variance = measurement_variance
        self.estimate: Optional[float] = None
        self.error_estimate: float = 1.0
    
    def update(self, measurement: float) -> float:
        """Update with new measurement and return filtered value"""
        if self.estimate is None:
            # First measurement
            self.estimate = measurement
            return self.estimate
        
        # Prediction step
        predicted_estimate = self.estimate
        predicted_error = self.error_estimate + self.process_variance
        
        # Update step
        kalman_gain = predicted_error / (predicted_error + self.measurement_variance)
        self.estimate = predicted_estimate + kalman_gain * (measurement - predicted_estimate)
        self.error_estimate = (1 - kalman_gain) * predicted_error
        
        return self.estimate
    
    def reset(self):
        """Reset the filter"""
        self.estimate = None
        self.error_estimate = 1.0


class CombinedRFFilter:
    """
    Combined filter using EMA + Median for robust RSSI smoothing
    
    Process:
    1. Median filter removes spikes/outliers
    2. EMA smooths the cleaned signal
    
    This combination is resistant to both outliers and fluctuations
    """
    
    def __init__(self, alpha: float = 0.3, window_size: int = 5):
        """
        Args:
            alpha: EMA smoothing factor (0.2-0.4 recommended)
            window_size: Median filter window (3-7 recommended)
        """
        self.median_filter = MedianFilter(window_size)
        self.ema_smoother = SignalSmoother(alpha)
    
    def update(self, rssi: float) -> float:
        """Update with new RSSI and return smoothed value"""
        # Step 1: Remove outliers with median filter
        median_filtered = self.median_filter.update(rssi)
        
        # Step 2: Smooth with EMA
        smoothed = self.ema_smoother.update(median_filtered)
        
        return smoothed
    
    def reset(self):
        """Reset both filters"""
        self.median_filter.reset()
        self.ema_smoother.reset()


class PerScannerRFFilter:
    """
    Manages separate filters for each scanner (left and right)
    
    Maintains independent filtering for each scanner to handle
    different RF environments and antenna characteristics
    """
    
    def __init__(self, alpha: float = 0.3, window_size: int = 5):
        """
        Args:
            alpha: EMA smoothing factor
            window_size: Median filter window size
        """
        self.filters: Dict[str, CombinedRFFilter] = {}
        self.alpha = alpha
        self.window_size = window_size
    
    def update(self, scanner_id: str, rssi: float) -> float:
        """
        Update filter for specific scanner
        
        Args:
            scanner_id: Scanner identifier (e.g., 'gate-left')
            rssi: Raw RSSI value
            
        Returns:
            Smoothed RSSI value
        """
        # Create filter for scanner if it doesn't exist
        if scanner_id not in self.filters:
            self.filters[scanner_id] = CombinedRFFilter(self.alpha, self.window_size)
        
        # Update and return smoothed value
        return self.filters[scanner_id].update(rssi)
    
    def reset_scanner(self, scanner_id: str):
        """Reset filter for specific scanner"""
        if scanner_id in self.filters:
            self.filters[scanner_id].reset()
    
    def reset_all(self):
        """Reset all scanner filters"""
        for filter in self.filters.values():
            filter.reset()


class AdaptiveRFFilter:
    """
    Adaptive filter that adjusts smoothing based on signal stability
    
    When signal is stable → less smoothing (faster response)
    When signal is noisy → more smoothing (better stability)
    """
    
    def __init__(self, base_alpha: float = 0.3, window_size: int = 5):
        """
        Args:
            base_alpha: Base smoothing factor
            window_size: Window for stability calculation
        """
        self.base_alpha = base_alpha
        self.window = deque(maxlen=window_size)
        self.smoother = SignalSmoother(base_alpha)
        self.median_filter = MedianFilter(window_size)
    
    def update(self, rssi: float) -> float:
        """Update with adaptive smoothing"""
        # Add to window for stability calculation
        self.window.append(rssi)
        
        # Calculate signal stability (variance)
        if len(self.window) >= 3:
            values = list(self.window)
            avg = sum(values) / len(values)
            variance = sum((x - avg) ** 2 for x in values) / len(values)
            
            # Adapt alpha based on variance
            # High variance (noisy) → lower alpha (more smoothing)
            # Low variance (stable) → higher alpha (less smoothing)
            if variance > 20:  # Very noisy
                alpha = 0.2
            elif variance > 10:  # Noisy
                alpha = 0.3
            elif variance > 5:  # Slightly noisy
                alpha = 0.4
            else:  # Stable
                alpha = 0.5
            
            self.smoother.alpha = alpha
        
        # Apply median then EMA
        median_filtered = self.median_filter.update(rssi)
        return self.smoother.update(median_filtered)
    
    def reset(self):
        """Reset the filter"""
        self.window.clear()
        self.smoother.reset()
        self.median_filter.reset()


def load_calibration_bias():
    """
    Load RSSI bias values from calibration file
    
    Returns:
        Dict with scanner biases, or empty dict if not calibrated
    """
    import os
    import json
    
    calib_file = "calibration/sessions/latest/calibration.json"
    
    if not os.path.exists(calib_file):
        return {}
    
    try:
        with open(calib_file, 'r') as f:
            calib_data = json.load(f)
        
        bias_comp = calib_data.get('bias_compensation', {})
        
        return {
            'gate-left': bias_comp.get('left_bias_db', 0.0),
            'gate-right': bias_comp.get('right_bias_db', 0.0)
        }
    except Exception as e:
        print(f"Warning: Failed to load calibration: {e}")
        return {}


def apply_bias_compensation(scanner_id: str, rssi: float, bias_map: Dict[str, float]) -> float:
    """
    Apply RSSI bias compensation
    
    Args:
        scanner_id: Scanner identifier
        rssi: Raw RSSI value
        bias_map: Map of scanner_id to bias value
        
    Returns:
        RSSI with bias applied
    """
    bias = bias_map.get(scanner_id, 0.0)
    return rssi + bias


# Example usage
if __name__ == '__main__':
    # Test signal smoothing
    import random
    
    print("Testing RF Signal Filters\n")
    
    # Simulate noisy RSSI readings
    base_rssi = -65
    noisy_readings = [base_rssi + random.gauss(0, 5) for _ in range(20)]
    
    # Test different filters
    filters = {
        'Raw': None,
        'EMA': SignalSmoother(alpha=0.3),
        'Median': MedianFilter(window_size=5),
        'Combined': CombinedRFFilter(alpha=0.3, window_size=5),
        'Adaptive': AdaptiveRFFilter()
    }
    
    print("Sample  Raw    EMA    Median Combined Adaptive")
    print("-" * 60)
    
    for i, raw in enumerate(noisy_readings):
        results = {'Raw': raw}
        
        for name, filter in filters.items():
            if filter is not None:
                results[name] = filter.update(raw)
        
        print(f"{i+1:2d}    {results['Raw']:6.1f} "
              f"{results.get('EMA', 0):6.1f} "
              f"{results.get('Median', 0):6.1f} "
              f"{results.get('Combined', 0):6.1f} "
              f"{results.get('Adaptive', 0):6.1f}")

