#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#include <vector>
#include <cmath>

namespace py = pybind11;

// 快速移动平均
// 修复后的快速移动平均
py::array_t<double> fast_sma(const py::array_t<double>& prices, int window) {
    auto buf = prices.request();
    double* ptr = static_cast<double*>(buf.ptr);
    size_t size = buf.size;
    
    py::array_t<double> result(size);
    auto result_buf = result.request();
    double* result_ptr = static_cast<double*>(result_buf.ptr);
    
    // 初始化所有值为NAN
    for (size_t i = 0; i < size; ++i) {
        result_ptr[i] = NAN;
    }
    
    // 如果数据长度小于窗口，直接返回全NaN
    if (size < static_cast<size_t>(window) || window <= 0) {
        return result;
    }
    
    // 计算第一个窗口的和
    double sum = 0.0;
    for (int i = 0; i < window; ++i) {
        sum += ptr[i];
    }
    
    // 第一个有效值在索引 window-1 处
    result_ptr[window - 1] = sum / window;
    
    // 使用滑动窗口计算其余值
    for (size_t i = window; i < size; ++i) {
        sum = sum - ptr[i - window] + ptr[i];
        result_ptr[i] = sum / window;
    }
    
    return result;
}

// 快速RSI计算
py::array_t<double> fast_rsi(const py::array_t<double>& prices, int period) {
    auto buf = prices.request();
    double* ptr = static_cast<double*>(buf.ptr);
    size_t size = buf.size;
    
    py::array_t<double> result(size);
    auto result_buf = result.request();
    double* result_ptr = static_cast<double*>(result_buf.ptr);
    
    std::vector<double> gains(size, 0.0);
    std::vector<double> losses(size, 0.0);
    
    // 计算涨跌幅
    for (size_t i = 1; i < size; ++i) {
        double change = ptr[i] - ptr[i-1];
        if (change > 0) {
            gains[i] = change;
            losses[i] = 0.0;
        } else {
            gains[i] = 0.0;
            losses[i] = -change;
        }
    }
    
    // 计算RSI
    for (size_t i = period; i < size; ++i) {
        double avg_gain = 0.0;
        double avg_loss = 0.0;
        
        for (int j = 0; j < period; ++j) {
            avg_gain += gains[i - j];
            avg_loss += losses[i - j];
        }
        
        avg_gain /= period;
        avg_loss /= period;
        
        if (avg_loss == 0.0) {
            result_ptr[i] = 100.0;
        } else {
            double rs = avg_gain / avg_loss;
            result_ptr[i] = 100.0 - (100.0 / (1.0 + rs));
        }
    }
    
    // 填充前period个值为NAN
    for (size_t i = 0; i < period; ++i) {
        result_ptr[i] = NAN;
    }
    
    return result;
}

// 模块定义 - 注意：字符串常量不能直接换行！
PYBIND11_MODULE(fast_factors, m) {
    // 文档字符串：要么单行，要么使用续行符
    m.doc() = "高性能量化因子计算模块 (AStock Quant Engine)";  // 单行
    
    // 或者使用续行符（\后不能有空格）
    m.attr("__version__") = "1.0.0";
    m.attr("__author__") = "AStock Quant Team";
    
    // 注册函数 - 使用英文文档字符串避免编码问题
    m.def("fast_sma", &fast_sma, 
        py::arg("prices"), 
        py::arg("window") = 20,
        R"(Calculate Simple Moving Average.
        
        Args:
            prices: numpy array of price data
            window: moving average window size
            
        Returns:
            numpy array of SMA values
        )");
    
    m.def("fast_rsi", &fast_rsi,
        py::arg("prices"),
        py::arg("period") = 14,
        R"(Calculate Relative Strength Index.
        
        Args:
            prices: numpy array of price data
            period: RSI calculation period (default 14)
            
        Returns:
            numpy array of RSI values
        )");
}