// pybindings_globalstate.cpp
#include <pybind11/pybind11.h>
#include <pybind11/functional.h>
#include <QObject>
#include "GlobalState.h"

namespace py = pybind11;

class PyGlobalState : public QObject {
    Q_OBJECT
public:
    PyGlobalState() : QObject(nullptr) {}

    bool usePreciseMatch() const { return GlobalState::instance().usePreciseMatch(); }
    void setUsePreciseMatch(bool v) { GlobalState::instance().setUsePreciseMatch(v); }

    QString token() const { return GlobalState::instance().token(); }
    void setToken(const QString& v) { GlobalState::instance().setToken(v); }

    QString accountId() const { return GlobalState::instance().accountId(); }
    void setAccountId(const QString& v) { GlobalState::instance().setAccountId(v); }

    // 信号转发到 Python
    void onUsePreciseMatchChanged(std::function<void(bool)> cb) {
        QObject::connect(&GlobalState::instance(), &GlobalState::usePreciseMatchChanged, cb);
    }
    void onTokenChanged(std::function<void(QString)> cb) {
        QObject::connect(&GlobalState::instance(), &GlobalState::tokenChanged, cb);
    }
    void onAccountIdChanged(std::function<void(QString)> cb) {
        QObject::connect(&GlobalState::instance(), &GlobalState::accountIdChanged, cb);
    }
};

PYBIND11_MODULE(_native, m) {
    py::class_<PyGlobalState, QObject>(m, "GlobalState")
        .def(py::init<>())
        .def_property("usePreciseMatch", &PyGlobalState::usePreciseMatch, &PyGlobalState::setUsePreciseMatch)
        .def_property("token", &PyGlobalState::token, &PyGlobalState::setToken)
        .def_property("accountId", &PyGlobalState::accountId, &PyGlobalState::setAccountId)
        .def("onUsePreciseMatchChanged", &PyGlobalState::onUsePreciseMatchChanged)
        .def("onTokenChanged", &PyGlobalState::onTokenChanged)
        .def("onAccountIdChanged", &PyGlobalState::onAccountIdChanged);
}
