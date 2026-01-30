// astock_engine/bindings/python_bindings.cpp
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/functional.h>
#include "EventSystem.hpp"
#include "EventBus.hpp"

namespace py = pybind11;

PYBIND11_MODULE(_native, m) {
    m.doc() = "ASTOCK Quant Engine Core";
    
    // ==== 导出 EventFormat ====
    py::class_<astock::EventFormat>(m, "EventFormat")
        .def(py::init<>())
        .def(py::init<const std::string&, const std::string&>())
        .def_readwrite("event_type", &astock::EventFormat::event_type)
        .def_readwrite("source", &astock::EventFormat::source)
        .def_readwrite("timestamp_us", &astock::EventFormat::timestamp_us)
        
        // 数据访问
        .def("get_string", [](const astock::EventFormat& self, 
                               const std::string& key) -> py::object {
            auto val = self.get<std::string>(key);
            if (val) return py::cast(*val);
            return py::none();
        })
        .def("get_int", [](const astock::EventFormat& self,
                           const std::string& key) -> py::object {
            auto val = self.get<int64_t>(key);
            if (val) return py::cast(*val);
            return py::none();
        })
        .def("get_double", [](const astock::EventFormat& self,
                              const std::string& key) -> py::object {
            auto val = self.get<double>(key);
            if (val) return py::cast(*val);
            return py::none();
        })
        .def("get_bool", [](const astock::EventFormat& self,
                            const std::string& key) -> py::object {
            auto val = self.get<bool>(key);
            if (val) return py::cast(*val);
            return py::none();
        })
        
        // 数据设置
        .def("set_string", [](astock::EventFormat& self,
                              const std::string& key,
                              const std::string& value) {
            self.set(key, value);
        })
        .def("set_int", [](astock::EventFormat& self,
                           const std::string& key,
                           int64_t value) {
            self.set(key, value);
        })
        .def("set_double", [](astock::EventFormat& self,
                              const std::string& key,
                              double value) {
            self.set(key, value);
        })
        .def("set_bool", [](astock::EventFormat& self,
                            const std::string& key,
                            bool value) {
            self.set(key, value);
        })
        
        .def("has", &astock::EventFormat::has)
        .def("to_json", &astock::EventFormat::to_json)
        .def("to_attributes", &astock::EventFormat::to_attributes)
        .def("__repr__", [](const astock::EventFormat& self) {
            return "EventFormat(type=" + self.event_type + 
                   ", source=" + self.source + 
                   ", timestamp=" + std::to_string(self.timestamp_us) + ")";
        });
    
    // ==== 导出 EventFactory ====
    py::class_<astock::EventFactory>(m, "EventFactory")
        .def_static("create_market_tick", &astock::EventFactory::create_market_tick,
                   py::arg("symbol"), py::arg("price"), py::arg("volume"),
                   py::arg("bid") = 0.0, py::arg("ask") = 0.0,
                   py::arg("bid_size") = 0, py::arg("ask_size") = 0)
        .def_static("create_market_bar", &astock::EventFactory::create_market_bar,
                   py::arg("symbol"), py::arg("interval"),
                   py::arg("open"), py::arg("high"), py::arg("low"), py::arg("close"),
                   py::arg("volume"), py::arg("bar_start"))
        .def_static("create_order_event", &astock::EventFactory::create_order_event,
                   py::arg("order_id"), py::arg("symbol"), py::arg("side"),
                   py::arg("order_type"), py::arg("price"), py::arg("quantity"),
                   py::arg("status"), py::arg("account") = "")
        .def_static("create_strategy_signal", &astock::EventFactory::create_strategy_signal,
                   py::arg("strategy_id"), py::arg("symbol"), py::arg("signal"),
                   py::arg("strength"), py::arg("price") = 0.0, 
                   py::arg("quantity") = 0);
    
    // ==== 导出 EventBus ====
    py::class_<astock::EventBus>(m, "EventBus")
        .def(py::init<>())
        .def(py::init<const astock::EventBus::Config&>())
        
        // 订阅管理
        .def("subscribe", &astock::EventBus::subscribe,
             py::arg("event_type"), py::arg("handler"),
             py::arg("filter") = nullptr, py::arg("priority") = 0)
        .def("unsubscribe", &astock::EventBus::unsubscribe)
        
        // 事件发布
        .def("publish", &astock::EventBus::publish)
        .def("publish_async", &astock::EventBus::publish_async)
        .def("publish_batch", &astock::EventBus::publish_batch)
        
        // 系统控制
        .def("start", &astock::EventBus::start)
        .def("stop", &astock::EventBus::stop)
        .def("wait_for_empty", &astock::EventBus::wait_for_empty,
             py::arg("timeout_seconds") = 5.0)
        .def("clear_queue", &astock::EventBus::clear_queue)
        
        // 状态查询
        .def("get_metrics", &astock::EventBus::get_metrics)
        .def("get_subscription_count", &astock::EventBus::get_subscription_count)
        .def("is_running", &astock::EventBus::is_running)
        
        // 配置
        .def("set_drop_policy_on_full", &astock::EventBus::set_drop_policy_on_full)
        .def("add_global_filter", &astock::EventBus::add_global_filter)
        
        .def("__repr__", [](const astock::EventBus&) {
            return "EventBus";
        });
    
    // ==== 导出 EventBus::Config ====
    py::class_<astock::EventBus::Config>(m, "EventBusConfig")
        .def(py::init<>())
        .def_readwrite("worker_threads", &astock::EventBus::Config::worker_threads)
        .def_readwrite("max_queue_size", &astock::EventBus::Config::max_queue_size)
        .def_readwrite("enable_priority_queue", &astock::EventBus::Config::enable_priority_queue)
        .def_readwrite("batch_size", &astock::EventBus::Config::batch_size)
        .def_readwrite("enable_metrics", &astock::EventBus::Config::enable_metrics);
    
    // ==== 导出 EventBus::Metrics ====
    py::class_<astock::EventBus::Metrics>(m, "EventBusMetrics")
        .def(py::init<>())
        .def_readwrite("total_events_published", &astock::EventBus::Metrics::total_events_published)
        .def_readwrite("total_events_processed", &astock::EventBus::Metrics::total_events_processed)
        .def_readwrite("current_queue_size", &astock::EventBus::Metrics::current_queue_size)
        .def_readwrite("max_queue_size", &astock::EventBus::Metrics::max_queue_size)
        .def_readwrite("handler_errors", &astock::EventBus::Metrics::handler_errors)
        .def_readwrite("avg_processing_time_us", &astock::EventBus::Metrics::avg_processing_time_us)
        .def_readwrite("active_subscriptions", &astock::EventBus::Metrics::active_subscriptions)
        .def("to_string", &astock::EventBus::Metrics::to_string)
        .def("reset", &astock::EventBus::Metrics::reset);
    
    // ==== 导出 EventType 常量 ====
    m.attr("EVENT_TYPE_SYSTEM_STARTUP") = py::cast(astock::EventType::SYSTEM_STARTUP);
    m.attr("EVENT_TYPE_SYSTEM_SHUTDOWN") = py::cast(astock::EventType::SYSTEM_SHUTDOWN);
    m.attr("EVENT_TYPE_MARKET_TICK") = py::cast(astock::EventType::MARKET_TICK);
    m.attr("EVENT_TYPE_MARKET_BAR_1M") = py::cast(astock::EventType::MARKET_BAR_1M);
    m.attr("EVENT_TYPE_MARKET_BAR_1D") = py::cast(astock::EventType::MARKET_BAR_1D);
    m.attr("EVENT_TYPE_ORDER_NEW") = py::cast(astock::EventType::ORDER_NEW);
    m.attr("EVENT_TYPE_ORDER_FILLED") = py::cast(astock::EventType::ORDER_FILLED);
    m.attr("EVENT_TYPE_STRATEGY_SIGNAL") = py::cast(astock::EventType::STRATEGY_SIGNAL);
    
    // ==== 导出 EventSource 常量 ====
    m.attr("EVENT_SOURCE_SYSTEM") = py::cast(astock::EventSource::SYSTEM);
    m.attr("EVENT_SOURCE_MARKET_DATA") = py::cast(astock::EventSource::MARKET_DATA);
    m.attr("EVENT_SOURCE_TRADING") = py::cast(astock::EventSource::TRADING);
    m.attr("EVENT_SOURCE_STRATEGY") = py::cast(astock::EventSource::STRATEGY);
    
    // ==== 工具函数 ====
    m.def("current_timestamp_us", &astock::EventFormat::current_timestamp,
          "Get current timestamp in microseconds");
}