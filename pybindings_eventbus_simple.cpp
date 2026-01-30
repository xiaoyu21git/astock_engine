// ASTOCK EventBus Python Bindings - 简化版 
// 只绑定核心功能，避免链接问题
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/functional.h>
#include "Event/EventBus.hpp"
#include "Event/EventFormat.hpp"
#include "foundation/Utils/Uuid.h"
#include <memory>
#include <chrono>

namespace py = pybind11;
using namespace engine;

PYBIND11_MODULE(eventbus_native, m) {
    m.doc() = "ASTOCK EventBus Native C++ Bindings - Simplified";

    // ===== 基础类型 =====
    py::class_<foundation::Uuid>(m, "Uuid")
        .def("__str__", [](const foundation::Uuid& uuid) {
            return uuid.to_string();
        })
        .def("__repr__", [](const foundation::Uuid& uuid) {
            return "<Uuid " + uuid.to_string() + ">";
        });

    // ===== 枚举类型 =====
    py::enum_<EventPriority>(m, "EventPriority")
        .value("CRITICAL", EventPriority::CRITICAL)
        .value("HIGH", EventPriority::HIGH)
        .value("NORMAL", EventPriority::NORMAL)
        .value("LOW", EventPriority::LOW)
        .value("BACKGROUND", EventPriority::BACKGROUND);

    py::enum_<Event_Core::EventSource>(m, "EventSource")
        .value("SYSTEM", Event_Core::EventSource::SYSTEM)
        .value("MARKET_DATA", Event_Core::EventSource::MARKET_DATA)
        .value("TRADING", Event_Core::EventSource::TRADING)
        .value("STRATEGY", Event_Core::EventSource::STRATEGY)
        .value("RISK", Event_Core::EventSource::RISK)
        .value("DATABASE", Event_Core::EventSource::DATABASE)
        .value("NETWORK", Event_Core::EventSource::NETWORK)
        .value("BACKTEST", Event_Core::EventSource::BACKTEST)
        .value("USER", Event_Core::EventSource::USER)
        .value("CUSTOM", Event_Core::EventSource::CUSTOM);

    py::enum_<PublishError>(m, "PublishError")
        .value("OK", PublishError::OK)
        .value("QUEUE_FULL", PublishError::QUEUE_FULL)
        .value("INVALID_SUBSCRIPTION", PublishError::INVALID_SUBSCRIPTION)
        .value("DISPATCHER_NOT_RUNNING", PublishError::DISPATCHER_NOT_RUNNING)
        .value("SERIALIZATION_FAILED", PublishError::SERIALIZATION_FAILED)
        .value("INTERNAL_ERROR", PublishError::INTERNAL_ERROR);

    py::class_<PublishResult>(m, "PublishResult")
        .def_readonly("error", &PublishResult::error)
        .def_readonly("message", &PublishResult::message)
        .def("is_ok", [](const PublishResult& r) { 
            return r.error == PublishError::OK; 
        })
        .def("__bool__", [](const PublishResult& r) { 
            return r.error == PublishError::OK; 
        });

    // ===== EventFormat - 最小接口 =====
    py::class_<EventFormat>(m, "EventFormat")
        .def(py::init([](const std::string& type_str, int source_int) {
            EventFormat evt;
            evt.type = type_str;
            evt.source = static_cast<Event_Core::EventSource>(source_int);
            evt.timestamp = std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::system_clock::now().time_since_epoch()
            ).count();
            return evt;
        }), py::arg("type"), py::arg("source") = 0)
        .def_readwrite("id", &EventFormat::id)
        .def_readwrite("type", &EventFormat::type)
        .def_readwrite("source", &EventFormat::source)
        .def_readwrite("priority", &EventFormat::priority)
        .def_readwrite("timestamp", &EventFormat::timestamp)
        .def_readwrite("created_at", &EventFormat::created_at)
        .def_readwrite("correlation_id", &EventFormat::correlation_id)
        .def_readwrite("metadata", &EventFormat::metadata)
        .def("has", &EventFormat::has, py::arg("key"))
        .def("remove", &EventFormat::remove, py::arg("key"))
        .def("has_data", &EventFormat::has_data)
        .def("has_metadata", &EventFormat::has_metadata)
        .def("__repr__", [](const EventFormat& e) {
            return "<EventFormat type='" + e.type + "' ts=" + 
                   std::to_string(e.timestamp) + ">";
        });

    // ===== EventBus::Config =====
    py::class_<EventBus::Config>(m, "EventBusConfig")
        .def(py::init<>())
        .def_readwrite("worker_threads", &EventBus::Config::worker_threads)
        .def_readwrite("max_queue_size", &EventBus::Config::max_queue_size)
        .def_readwrite("enable_priority_queue", &EventBus::Config::enable_priority_queue)
        .def_readwrite("batch_size", &EventBus::Config::batch_size);

    // ===== EventBus - 核心接口 =====
    py::class_<EventBus, std::unique_ptr<EventBus, py::nodelete>>(m, "EventBus")
        .def_static("create", 
            [](const EventBus::Config& config) {
                return EventBus::create(config).release();
            },
            py::arg("config") = EventBus::Config(),
            py::return_value_policy::take_ownership)
        .def("start", &EventBus::start)
        .def("stop", &EventBus::stop, 
            py::arg("wait_completion") = true, 
            py::arg("timeout_ms") = 5000)
        .def("is_running", &EventBus::is_running)
        .def("reset", &EventBus::reset)
        .def("publish", 
            [](EventBus& self, const EventFormat& event, int priority) {
                return self.publish(event, priority);
            },
            py::arg("event"), 
            py::arg("priority") = 5)
        .def("subscribe", 
            [](EventBus& self, 
               const std::string& event_type,
               py::function handler,
               int priority) {
                EventFormatHandler cpp_handler = [handler](const EventFormat& evt) {
                    py::gil_scoped_acquire acquire;
                    try {
                        handler(evt);
                    } catch (py::error_already_set& e) {
                        py::print("Error in handler:", e.what());
                    }
                };
                return self.subscribe(event_type, cpp_handler, nullptr, priority);
            },
            py::arg("event_type"),
            py::arg("handler"),
            py::arg("priority") = 0)
        .def("unsubscribe", 
            [](EventBus& self, const foundation::Uuid& subscription_id) {
                return self.unsubscribe(subscription_id);
            },
            py::arg("subscription_id"))
        .def("wait_for_empty", &EventBus::wait_for_empty,
            py::arg("timeout_seconds") = 5.0)
        .def("__repr__", [](const EventBus& bus) {
            return "<EventBus running=" + 
                   std::string(bus.is_running() ? "True" : "False") + ">";
        });

    // ===== 工具函数 =====
    m.def("get_timestamp_us", []() {
        return std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::system_clock::now().time_since_epoch()
        ).count();
    });

    m.attr("__version__") = "1.0.0-simple";
}
