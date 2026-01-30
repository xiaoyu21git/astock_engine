// ASTOCK Quant Engine Python Bindings - EventBus Module
// 将 C++ EventBus 绑定到 Python (匹配实际C++接口)
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/functional.h>
#include <pybind11/chrono.h>
#include "Event/EventBus.hpp"
#include "Event/Event.h"
#include "Event/EventFormat.hpp"
#include "foundation/Utils/Uuid.h"
#include <memory>

namespace py = pybind11;
using namespace engine;

// EventBus Python 绑定模块
PYBIND11_MODULE(eventbus_native, m) {
    m.doc() = "ASTOCK EventBus Native C++ Bindings";

    // ===== EventPriority 枚举 =====
    py::enum_<EventPriority>(m, "EventPriority")
        .value("CRITICAL", EventPriority::CRITICAL)
        .value("HIGH", EventPriority::HIGH)
        .value("NORMAL", EventPriority::NORMAL)
        .value("LOW", EventPriority::LOW)
        .value("BACKGROUND", EventPriority::BACKGROUND);

    // ===== EventSource 枚举 =====
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

    // ===== EventFormat 绑定 =====
    py::class_<EventFormat>(m, "EventFormat")
        .def(py::init<std::string, Event_Core::EventSource>(),
            py::arg("event_type"),
            py::arg("source"))
        .def(py::init<std::string, std::string, int64_t>(),
            py::arg("event_type"),
            py::arg("source_str"),
            py::arg("timestamp_us") = 0)
        .def_readwrite("id", &EventFormat::id)
        .def_readwrite("type", &EventFormat::type)
        .def_readwrite("source", &EventFormat::source)
        .def_readwrite("priority", &EventFormat::priority)
        .def_readwrite("timestamp", &EventFormat::timestamp)
        .def_readwrite("created_at", &EventFormat::created_at)
        .def_readwrite("correlation_id", &EventFormat::correlation_id)
        .def_readwrite("metadata", &EventFormat::metadata)
        .def("generate_id", &EventFormat::generate_id)
        .def("has", &EventFormat::has, py::arg("key"))
        .def("remove", &EventFormat::remove, py::arg("key"))
        .def("to_json", &EventFormat::to_json)
        .def("to_string", &EventFormat::to_string)
        .def("has_data", &EventFormat::has_data)
        .def("has_metadata", &EventFormat::has_metadata)
        .def_static("from_json", &EventFormat::from_json)
        .def_static("create_from_strings", &EventFormat::create_from_strings,
            py::arg("event_type"),
            py::arg("source_str"),
            py::arg("timestamp_us") = 0)
        .def("__repr__", [](const EventFormat& e) {
            return "<EventFormat type='" + e.type + "' ts=" + 
                   std::to_string(e.timestamp) + ">";
        });

    // ===== PublishError 枚举 =====
    py::enum_<PublishError>(m, "PublishError")
        .value("OK", PublishError::OK)
        .value("QUEUE_FULL", PublishError::QUEUE_FULL)
        .value("INVALID_SUBSCRIPTION", PublishError::INVALID_SUBSCRIPTION)
        .value("DISPATCHER_NOT_RUNNING", PublishError::DISPATCHER_NOT_RUNNING)
        .value("SERIALIZATION_FAILED", PublishError::SERIALIZATION_FAILED)
        .value("INTERNAL_ERROR", PublishError::INTERNAL_ERROR);

    // ===== PublishResult 绑定 =====
    py::class_<PublishResult>(m, "PublishResult")
        .def_readonly("error", &PublishResult::error)
        .def_readonly("message", &PublishResult::message)
        .def("__bool__", [](const PublishResult& r) { 
            return bool(r); 
        })
        .def("is_ok", [](const PublishResult& r) { 
            return r.error == PublishError::OK; 
        });

    // ===== Uuid 绑定 (订阅ID) =====
    py::class_<foundation::Uuid>(m, "Uuid")
        .def("__str__", [](const foundation::Uuid& uuid) {
            return uuid.to_string();
        })
        .def("__repr__", [](const foundation::Uuid& uuid) {
            return "<Uuid " + uuid.to_string() + ">";
        });

    // ===== EventBus::Config 绑定 =====
    py::class_<EventBus::Config>(m, "EventBusConfig")
        .def(py::init<>())
        .def_readwrite("worker_threads", &EventBus::Config::worker_threads)
        .def_readwrite("max_queue_size", &EventBus::Config::max_queue_size)
        .def_readwrite("enable_priority_queue", &EventBus::Config::enable_priority_queue)
        .def_readwrite("batch_size", &EventBus::Config::batch_size)
        .def_readwrite("enable_event_format", &EventBus::Config::enable_event_format)
        .def_readwrite("auto_convert_formats", &EventBus::Config::auto_convert_formats)
        .def_readwrite("drop_oldest_on_full", &EventBus::Config::drop_oldest_on_full);

    // ===== EventBus 绑定 =====
    py::class_<EventBus, std::unique_ptr<EventBus, py::nodelete>>(m, "EventBus")
        .def_static("create", 
            [](const EventBus::Config& config) {
                return EventBus::create(config).release();
            },
            py::arg("config") = EventBus::Config(),
            py::return_value_policy::take_ownership,
            "Create EventBus instance")
        .def("start", &EventBus::start,
            "Start the event bus")
        .def("stop", &EventBus::stop, 
            py::arg("wait_completion") = true, 
            py::arg("timeout_ms") = 5000,
            "Stop the event bus")
        .def("is_running", &EventBus::is_running,
            "Check if event bus is running")
        .def("reset", &EventBus::reset,
            "Reset event bus (clear queues and subscriptions)")
        .def("publish", 
            [](EventBus& self, const EventFormat& event, int priority) {
                return self.publish(event, priority);
            },
            py::arg("event"), 
            py::arg("priority") = 5,
            "Publish an EventFormat")
        .def("publish_batch", &EventBus::publish_batch,
            py::arg("events"),
            "Publish batch of EventFormats")
        .def("subscribe", 
            [](EventBus& self, 
               const std::string& event_type,
               py::function handler,
               int priority) {
                // 包装 Python 回调
                EventFormatHandler cpp_handler = [handler](const EventFormat& evt) {
                    py::gil_scoped_acquire acquire;
                    try {
                        handler(evt);
                    } catch (py::error_already_set& e) {
                        py::print("Error in event handler:", e.what());
                    }
                };
                return self.subscribe(event_type, cpp_handler, nullptr, priority);
            },
            py::arg("event_type"),
            py::arg("handler"),
            py::arg("priority") = 0,
            "Subscribe to events")
        .def("unsubscribe", 
            [](EventBus& self, const foundation::Uuid& subscription_id) {
                return self.unsubscribe(subscription_id);
            },
            py::arg("subscription_id"),
            "Unsubscribe from events")
        .def("dispatch", &EventBus::dispatch,
            "Manually dispatch queued events (sync mode)")
        .def("wait_for_empty", &EventBus::wait_for_empty,
            py::arg("timeout_seconds") = 5.0,
            "Wait for event queue to be empty")
        .def("__repr__", [](const EventBus& bus) {
            return "<EventBus running=" + 
                   std::string(bus.is_running() ? "True" : "False") + ">";
        });

    // ===== 便捷函数 =====
    m.def("create_event", 
        [](const std::string& type, const std::string& source) {
            return EventFormat::create_from_strings(type, source);
        }, 
        py::arg("type"),
        py::arg("source"),
        "Create a new EventFormat");

    m.def("get_timestamp_us", []() {
        return std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::system_clock::now().time_since_epoch()
        ).count();
    }, "Get current timestamp in microseconds");

    m.attr("__version__") = "1.0.0";
}
