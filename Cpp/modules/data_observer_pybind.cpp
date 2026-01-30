// data_observer_pybind.cpp
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/functional.h>
#include "data_observer.h"
#include "kline_observer.h"
#include "tick_observer.h"
#include "storage_observer.h"
#include "alert_observer.h"
#include "observer_factory.h"

namespace py = pybind11;

PYBIND11_MODULE(astock_observer, m) {
    m.doc() = "ASTOCK Data Observer Module";
    
    // DataEventType 枚举
    py::enum_<astock::market::observer::DataEventType>(m, "DataEventType")
        .value("KLINE_UPDATE", astock::market::observer::DataEventType::KLINE_UPDATE)
        .value("KLINE_COMPLETE", astock::market::observer::DataEventType::KLINE_COMPLETE)
        .value("TICK_UPDATE", astock::market::observer::DataEventType::TICK_UPDATE)
        .value("SYMBOL_ADDED", astock::market::observer::DataEventType::SYMBOL_ADDED)
        .value("SYMBOL_REMOVED", astock::market::observer::DataEventType::SYMBOL_REMOVED)
        .value("DATA_ERROR", astock::market::observer::DataEventType::DATA_ERROR)
        .value("CONNECTION_CHANGE", astock::market::observer::DataEventType::CONNECTION_CHANGE)
        .value("MARKET_OPEN", astock::market::observer::DataEventType::MARKET_OPEN)
        .value("MARKET_CLOSE", astock::market::observer::DataEventType::MARKET_CLOSE)
        .value("CUSTOM_EVENT", astock::market::observer::DataEventType::CUSTOM_EVENT)
        .export_values();
    
    // DataEvent 结构
    py::class_<astock::market::observer::DataEvent>(m, "DataEvent")
        .def(py::init<>())
        .def_readwrite("type", &astock::market::observer::DataEvent::type)
        .def_readwrite("symbol", &astock::market::observer::DataEvent::symbol)
        .def_readwrite("timestamp", &astock::market::observer::DataEvent::timestamp)
        .def_readwrite("event_id", &astock::market::observer::DataEvent::event_id)
        .def_readwrite("source", &astock::market::observer::DataEvent::source)
        .def_readwrite("message", &astock::market::observer::DataEvent::message)
        .def_readwrite("custom_data", &astock::market::observer::DataEvent::custom_data)
        .def("is_kline_event", &astock::market::observer::DataEvent::is_kline_event)
        .def("is_tick_event", &astock::market::observer::DataEvent::is_tick_event)
        .def("is_error_event", &astock::market::observer::DataEvent::is_error_event)
        .def("is_connection_event", &astock::market::observer::DataEvent::is_connection_event)
        .def("__str__", &astock::market::observer::DataEvent::to_string);
    
    // IDataObserver 接口
    py::class_<astock::market::observer::IDataObserver, 
               std::shared_ptr<astock::market::observer::IDataObserver>>(m, "IDataObserver")
        .def("on_data_event", &astock::market::observer::IDataObserver::on_data_event)
        .def("get_name", &astock::market::observer::IDataObserver::get_name)
        .def("get_description", &astock::market::observer::IDataObserver::get_description)
        .def("is_active", &astock::market::observer::IDataObserver::is_active)
        .def("set_active", &astock::market::observer::IDataObserver::set_active);
    
    // BaseDataObserver
    py::class_<astock::market::observer::BaseDataObserver,
               astock::market::observer::IDataObserver,
               std::shared_ptr<astock::market::observer::BaseDataObserver>>(m, "BaseDataObserver")
        .def(py::init<const std::string&, const std::string&>(),
             py::arg("name"), py::arg("description") = "")
        .def("set_config", &astock::market::observer::BaseDataObserver::set_config)
        .def("get_config", &astock::market::observer::BaseDataObserver::get_config)
        .def("add_event_filter", &astock::market::observer::BaseDataObserver::add_event_filter)
        .def("add_symbol_filter", &astock::market::observer::BaseDataObserver::add_symbol_filter)
        .def("clear_filters", &astock::market::observer::BaseDataObserver::clear_filters)
        .def("get_stats", &astock::market::observer::BaseDataObserver::get_stats)
        .def("reset_stats", &astock::market::observer::BaseDataObserver::reset_stats);
    
    // DataEventBus
    py::class_<astock::market::observer::DataEventBus>(m, "DataEventBus")
        .def_static("instance", &astock::market::observer::DataEventBus::instance,
                   py::return_value_policy::reference)
        .def("register_observer", py::overload_cast<
             astock::market::observer::DataEventBus::ObserverPtr>(
             &astock::market::observer::DataEventBus::register_observer))
        .def("register_observer", py::overload_cast<
             astock::market::observer::DataEventBus::ObserverPtr,
             astock::market::observer::DataEventType>(
             &astock::market::observer::DataEventBus::register_observer))
        .def("register_observer", py::overload_cast<
             astock::market::observer::DataEventBus::ObserverPtr,
             const std::string&>(
             &astock::market::observer::DataEventBus::register_observer))
        .def("register_observer", py::overload_cast<
             astock::market::observer::DataEventBus::ObserverPtr,
             astock::market::observer::DataEventType,
             const std::string&>(
             &astock::market::observer::DataEventBus::register_observer))
        .def("unregister_observer", py::overload_cast<
             astock::market::observer::DataEventBus::ObserverPtr>(
             &astock::market::observer::DataEventBus::unregister_observer))
        .def("register_handler", &astock::market::observer::DataEventBus::register_handler)
        .def("unregister_handler", &astock::market::observer::DataEventBus::unregister_handler)
        .def("publish_event", &astock::market::observer::DataEventBus::publish_event)
        .def("publish_event_async", &astock::market::observer::DataEventBus::publish_event_async)
        .def("publish_events", &astock::market::observer::DataEventBus::publish_events)
        .def("get_observer_count", &astock::market::observer::DataEventBus::get_observer_count)
        .def("get_handler_count", &astock::market::observer::DataEventBus::get_handler_count)
        .def("clear", &astock::market::observer::DataEventBus::clear)
        .def("get_stats", &astock::market::observer::DataEventBus::get_stats)
        .def("reset_stats", &astock::market::observer::DataEventBus::reset_stats);
    
    // 观察者工厂
    py::class_<astock::market::observer::ObserverFactory>(m, "ObserverFactory")
        .def_static("create_kline_observer", &astock::market::observer::ObserverFactory::create_kline_observer,
                   py::arg("name") = "KLineObserver",
                   py::arg("description") = "K线数据观察者")
        .def_static("create_tick_observer", &astock::market::observer::ObserverFactory::create_tick_observer,
                   py::arg("name") = "TickObserver",
                   py::arg("description") = "Tick数据观察者")
        .def_static("register_to_event_bus", &astock::market::observer::ObserverFactory::register_to_event_bus)
        .def_static("unregister_from_event_bus", &astock::market::observer::ObserverFactory::unregister_from_event_bus)
        .def_static("create_default_observers", &astock::market::observer::ObserverFactory::create_default_observers);
}