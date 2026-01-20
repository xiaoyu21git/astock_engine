// python_bindings/modules/market_data_module.cpp
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/chrono.h>
#include "engine/data/MarketDataManager.h"
#include "domain/market/DataType.h"

namespace py = pybind11;

// KLine的Python绑定
void bind_kline(py::module &m) {
    py::class_<astock::market::KLine>(m, "KLine")
        .def(py::init<>())
        .def_readwrite("symbol", &astock::market::KLine::symbol)
        .def_readwrite("period", &astock::market::KLine::period)
        .def_readwrite("timestamp", &astock::market::KLine::timestamp)
        .def_readwrite("open", &astock::market::KLine::open)
        .def_readwrite("high", &astock::market::KLine::high)
        .def_readwrite("low", &astock::market::KLine::low)
        .def_readwrite("close", &astock::market::KLine::close)
        .def_readwrite("volume", &astock::market::KLine::volume)
        .def_readwrite("amount", &astock::market::KLine::amount)
        .def_readwrite("turnover", &astock::market::KLine::turnover)
        .def("change_rate", &astock::market::KLine::change_rate)
        .def("is_yang", &astock::market::KLine::is_yang)
        .def("__repr__", [](const astock::market::KLine &kline) {
            return "<KLine " + kline.symbol + " " + 
                   std::to_string(kline.close) + " @ " + 
                   std::to_string(kline.timestamp) + ">";
        });
}

// MarketDataManager的Python绑定
void bind_market_data_manager(py::module &m) {
    py::class_<astock::engine::MarketDataManager>(m, "MarketDataManager")
        .def_static("get_instance", &astock::engine::MarketDataManager::get_instance,
                   py::return_value_policy::reference)
        .def("subscribe", &astock::engine::MarketDataManager::subscribe,
             py::arg("symbol"), py::arg("period") = "1m")
        .def("unsubscribe", &astock::engine::MarketDataManager::unsubscribe)
        .def("get_history_klines", &astock::engine::MarketDataManager::get_history_klines,
             py::arg("symbol"), py::arg("period"), 
             py::arg("start_time"), py::arg("end_time"),
             py::arg("limit") = 1000)
        .def("get_latest_kline", &astock::engine::MarketDataManager::get_latest_kline,
             py::arg("symbol"), py::arg("period") = "1m")
        .def("get_latest_tick", &astock::engine::MarketDataManager::get_latest_tick);
}

// 初始化市场数据模块
void init_market_data_module(py::module &m) {
    auto market = m.def_submodule("market", "Market data module");
    
    // 绑定数据类型
    bind_kline(market);
    
    // 绑定数据管理器
    bind_market_data_manager(market);
    
    // 便捷函数
    market.def("subscribe", [](const std::string& symbol, const std::string& period = "1m") {
        return astock::engine::MarketDataManager::get_instance().subscribe(symbol, period);
    });
    
    market.def("get_history", [](const std::string& symbol, const std::string& period,
                                uint64_t start_time, uint64_t end_time, int limit = 1000) {
        return astock::engine::MarketDataManager::get_instance()
            .get_history_klines(symbol, period, start_time, end_time, limit);
    });
}