# This Python file uses the following encoding: utf-8
import mock
import unittest
import primo
import datetime
import threading
import time
import psutil
import functools

TEST_PROCESS_NAME = "notepad.exe"
TEST_PROCESS_PATH = r"C:\Windows\System32\notepad.exe"

def mock_datetime(fake_date_obj):
    def decorator(function):
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            datetime_patcher = mock.patch.object(
                primo.datetime, 'datetime',
                mock.Mock(wraps=datetime.datetime)
            )

            mocked_datetime = datetime_patcher.start()
            mocked_datetime.today.return_value = fake_date_obj
            mocked_datetime.now.return_value = fake_date_obj

            return function(*args, **kwargs)
        return wrapper
    return decorator

def PrimoWorkerFnc(primo):
    primo.run()

# <UnitOfWorkName>_ScenarioUnderTest_ExpectedBehavior
class PrimoTests(unittest.TestCase):
    def tearDown(self):
        for proc in psutil.process_iter():
            if proc.name() == TEST_PROCESS_NAME:
                proc.kill()

    # DaysToRun Sozinho
    # Sexta
    @mock_datetime(datetime.datetime(2019, 12, 6))
    def test_DaysToRun_WhenInDaysToRun_ShouldInitializeTheProcess(self):
        xml_s = '''<?xml version="1.0"?>
        <Primo>
            <Parameters>
                <Parameter name="workdays" value="mon,tu,wed,th,fri" />
            </Parameters>

            <Process bin="'''+TEST_PROCESS_PATH+'''" id="tio_log_replay">
                <DaysToRun days="{workdays}" />
            </Process>
        </Primo>
        '''

        args = []
        x = primo.XmlConfigParser(args)
        testing_object = x.parse_string(xml_s)

        primo_t = threading.Thread(target=PrimoWorkerFnc, args=(testing_object,))
        primo_t.daemon = True
        primo_t.start()
        primo_t.join(2)

        proc = testing_object.processes['tio_log_replay']

        # Chama Stop do primo para sair do loop principal
        testing_object.Stop()

        self.assertTrue(proc is not None)
        self.assertEqual(True, proc.running)
        self.assertTrue(proc.days_to_run is not None)

    # DaysToRun Sozinho
    # Sabado
    @mock_datetime(datetime.datetime(2019, 12, 7))
    def test_DaysToRun_WhenNotInDaysToRun_ShouldNotInitialiazeTheProcess(self):
        xml_s = '''<?xml version="1.0"?>
        <Primo>
            <Parameters>
                <Parameter name="workdays" value="mon,tu,wed,th,fri" />
            </Parameters>

            <Process bin="'''+TEST_PROCESS_PATH+'''" id="tio_log_replay">
                <DaysToRun days="{workdays}" />
            </Process>
        </Primo>
        '''

        args = []
        x = primo.XmlConfigParser(args)
        testing_object = x.parse_string(xml_s)

        primo_t = threading.Thread(target=PrimoWorkerFnc, args=(testing_object,))
        primo_t.daemon = True
        primo_t.start()
        primo_t.join(2)

        proc = testing_object.processes['tio_log_replay']

        # Chama Stop do primo para sair do loop principal
        testing_object.Stop()

        self.assertTrue(proc is not None)
        self.assertEqual(False, proc.running)
        self.assertTrue(proc.days_to_run is not None)

    # OnSpecificTime Sozinho
    # Segunda
    # #obs: Por causa do loop principal, a data mockada para esse teste
    # #     especificamente precisa ser menor igual do que o dia corrente.
    @mock_datetime(datetime.datetime(2019, 12, 5, 6, 54, 0))
    def test_OnSpecificTime_WhenOnSpecificTime_ShouldInitialiazeTheProcess(self):
        xml_s = '''<?xml version="1.0"?>
        <Primo>
            <Parameters>
                <Parameter name="tio_log_replay_start_time" value="06:54:00" />
            </Parameters>

            <Process bin="'''+TEST_PROCESS_PATH+'''" id="tio_log_replay">
                <OnSpecificTime time="{tio_log_replay_start_time}" action="{process.Start()}" />
            </Process>
        </Primo>
        '''

        args = []
        x = primo.XmlConfigParser(args)
        testing_object = x.parse_string(xml_s)

        primo_t = threading.Thread(target=PrimoWorkerFnc, args=(testing_object,))
        primo_t.daemon = True
        primo_t.start()
        primo_t.join(2)

        proc = testing_object.processes['tio_log_replay']

        testing_object.Stop()

        self.assertTrue(proc is not None)
        self.assertEqual(True, proc.running)
        self.assertTrue(proc.on_specific_time is not None)

    # OnSpecificTime Sozinho
    # Segunda
    @mock_datetime(datetime.datetime(2019, 12, 7, 6, 52, 0))
    def test_OnSpecificTime_WhenNotOnSpecificTime_ShouldNotInitialiazeTheProcess(self):
        xml_s = '''<?xml version="1.0"?>
        <Primo>
            <Parameters>
                <Parameter name="tio_log_replay_start_time" value="06:54:00" />
            </Parameters>

            <Process bin="'''+TEST_PROCESS_PATH+'''" id="tio_log_replay">
                <OnSpecificTime time="{tio_log_replay_start_time}" action="{process.Start()}" />
            </Process>
        </Primo>
        '''

        args = []
        x = primo.XmlConfigParser(args)
        testing_object = x.parse_string(xml_s)

        primo_t = threading.Thread(target=PrimoWorkerFnc, args=(testing_object,))
        primo_t.daemon = True
        primo_t.start()
        primo_t.join(2)

        proc = testing_object.processes['tio_log_replay']

        testing_object.Stop()

        self.assertTrue(proc is not None)
        self.assertEqual(False, proc.running)
        self.assertTrue(proc.on_specific_time is not None)

    # Cenario DaysNotToRun sozinho
    # Sexta
    @mock_datetime(datetime.datetime(2019, 12, 6))
    def test_DaysNotToRun_WhenInDaysNotToRun_ShouldNotInitializeTheProcess(self):
        xml_s = '''<?xml version="1.0"?>
        <Primo>
            <Parameters>
                <Parameter name="workdays" value="mon,tu,wed,th,fri" />
            </Parameters>

            <Process bin="'''+TEST_PROCESS_PATH+'''" id="tio_log_replay">
                <DaysNotToRun days="{workdays}" />
            </Process>
        </Primo>
        '''

        args = []
        x = primo.XmlConfigParser(args)
        testing_object = x.parse_string(xml_s)

        primo_t = threading.Thread(target=PrimoWorkerFnc, args=(testing_object,))
        primo_t.daemon = True
        primo_t.start()
        primo_t.join(2)

        proc = testing_object.processes['tio_log_replay']

        # Chama Stop do primo para sair do loop principal
        testing_object.Stop()

        self.assertTrue(proc is not None)
        self.assertEqual(False, proc.running)

    # Cenario DaysNotToRun e DaysToRun em conflito
    # DaysNotToRun tem prioridade no codigo; atualmente 04/12/2019
    # Sabado
    # Dia de mock na bolsa
    @mock_datetime(datetime.datetime(2019, 12, 7))
    def test_DaysNotToRunAndDaysToRun_WhenInDaysToRunAndDayOfMockTest_ShouldNotInitializeTheProcess(self):
        xml_s = '''<?xml version="1.0"?>
        <Primo>
            <Parameters>
                <Parameter name="mockdays" value="2019-12-7" />
                <Parameter name="weekend" value="sun,sat" />
            </Parameters>

            <Process bin="'''+TEST_PROCESS_PATH+'''" id="tio_log_replay">
                <DaysNotToRun days="{mockdays}" />
                <DaysToRun days="{weekend}" />
            </Process>
        </Primo>
        '''

        args = []
        x = primo.XmlConfigParser(args)
        testing_object = x.parse_string(xml_s)

        primo_t = threading.Thread(target=PrimoWorkerFnc, args=(testing_object,))
        primo_t.daemon = True
        primo_t.start()
        primo_t.join(2)

        proc = testing_object.processes['tio_log_replay']

        testing_object.Stop()

        self.assertTrue(proc is not None)
        self.assertEqual(False, proc.running)
        self.assertTrue(proc.days_to_run is not None)
        self.assertTrue(proc.days_not_to_run is not None)

    # Cenario DaysNotToRun e DaysToRun em conflito
    # DaysNotToRun tem prioridade no codigo; atualmente 04/12/2019
    # Domingo
    # Mock test foi no dia anterior
    @mock_datetime(datetime.datetime(2019, 12, 8))
    def test_DaysNotToRunAndDaysToRun_WhenInDaysToRun_ShouldInitializeTheProcess(self):
        xml_s = '''<?xml version="1.0"?>
        <Primo>
            <Parameters>
                <Parameter name="mockdays" value="2019-12-7" />
                <Parameter name="weekend" value="sun,sat" />
            </Parameters>

            <Process bin="'''+TEST_PROCESS_PATH+'''" id="tio_log_replay">
                <DaysNotToRun days="{mockdays}" />
                <DaysToRun days="{weekend}" />
            </Process>
        </Primo>
        '''

        args = []
        x = primo.XmlConfigParser(args)
        testing_object = x.parse_string(xml_s)

        primo_t = threading.Thread(target=PrimoWorkerFnc, args=(testing_object,))
        primo_t.daemon = True
        primo_t.start()
        primo_t.join(2)

        proc = testing_object.processes['tio_log_replay']

        testing_object.Stop()

        self.assertTrue(proc is not None)
        self.assertEqual(True, proc.running)
        self.assertTrue(proc.days_to_run is not None)
        self.assertTrue(proc.days_not_to_run is not None)


    # Cenario DaysNotToRun + DaysToRun + OnSpecificTime
    # Sabado
    @mock_datetime(datetime.datetime(2019, 12, 7, 6, 52, 0))
    def test_DaysNotToRunAndDaysToRunAndOnSpecificTime_WhenNotOnSpecificTime_ShouldNotInitializeTheProcess(self):
        xml_s = '''<?xml version="1.0"?>
        <Primo>
            <Parameters>
                <Parameter name="mockdays" value="2019-12-15" />
                <Parameter name="weekend" value="sun,sat" />
                <Parameter name="tio_log_replay_start_time" value="06:54:00" />
            </Parameters>

            <Process bin="'''+TEST_PROCESS_PATH+'''" id="tio_log_replay">
                <DaysNotToRun days="{mockdays}" />
                <DaysToRun days="{weekend}" />
                <OnSpecificTime time="{tio_log_replay_start_time}" action="{process.Start()}" />
            </Process>
        </Primo>
        '''

        args = []
        x = primo.XmlConfigParser(args)
        testing_object = x.parse_string(xml_s)

        primo_t = threading.Thread(target=PrimoWorkerFnc, args=(testing_object,))
        primo_t.daemon = True
        primo_t.start()
        primo_t.join(2)

        proc = testing_object.processes['tio_log_replay']

        testing_object.Stop()

        self.assertTrue(proc is not None)
        self.assertEqual(False, proc.running)
        self.assertTrue(proc.days_to_run is not None)
        self.assertTrue(proc.days_not_to_run is not None)
        self.assertTrue(proc.on_specific_time is not None)


    # Cenario DaysNotToRun + DaysToRun + OnSpecificTime
    # Sabado
    @mock_datetime(datetime.datetime(2019, 12, 7, 6, 54, 0))
    def test_DaysNotToRunAndDaysToRunAndOnSpecificTime_WhenOnSpecificTime_ShouldInitializeTheProcess(self):
        xml_s = '''<?xml version="1.0"?>
        <Primo>
            <Parameters>
                <Parameter name="mockdays" value="2019-12-15" />
                <Parameter name="weekend" value="sun,sat" />
                <Parameter name="tio_log_replay_start_time" value="06:54:00" />
            </Parameters>

            <Process bin="'''+TEST_PROCESS_PATH+'''" id="tio_log_replay">
                <DaysNotToRun days="{mockdays}" />
                <DaysToRun days="{weekend}" />
                <OnSpecificTime time="{tio_log_replay_start_time}" action="{process.Start()}" />
            </Process>
        </Primo>
        '''

        args = []
        x = primo.XmlConfigParser(args)
        testing_object = x.parse_string(xml_s)

        primo_t = threading.Thread(target=PrimoWorkerFnc, args=(testing_object,))
        primo_t.daemon = True
        primo_t.start()
        primo_t.join(2)

        proc = testing_object.processes['tio_log_replay']

        testing_object.Stop()

        self.assertTrue(proc is not None)
        self.assertEqual(True, proc.running)
        self.assertTrue(proc.days_to_run is not None)
        self.assertTrue(proc.days_not_to_run is not None)
        self.assertTrue(proc.on_specific_time is not None)

    # Cenario DaysToRun + RunningPeriod
    # Sabado 06:54:00
    @mock_datetime(datetime.datetime(2019, 12, 7, 6, 54, 0))
    def test_DaysToRunAndRunningPeriod_WhenInDaysToRunAndNotInPeriod_ShouldNotInitializeTheProcess(self):
        xml_s = '''<?xml version="1.0"?>
        <Primo>
            <Parameters>
                <Parameter name="weekend" value="sun,sat" />
                <Parameter name="tio_log_replay_start_time" value="06:55:00" />
                <Parameter name="tio_log_replay_end_time" value="07:05:00"/>
            </Parameters>

            <Process bin="'''+TEST_PROCESS_PATH+'''" id="tio_log_replay">
                <DaysToRun days="{weekend}" />
                <RunningPeriod start="{tio_log_replay_start_time}" end="{tio_log_replay_end_time}"/>
            </Process>
        </Primo>
        '''

        args = []
        x = primo.XmlConfigParser(args)
        testing_object = x.parse_string(xml_s)

        primo_t = threading.Thread(target=PrimoWorkerFnc, args=(testing_object,))
        primo_t.daemon = True
        primo_t.start()
        primo_t.join(2)

        proc = testing_object.processes['tio_log_replay']

        testing_object.Stop()

        self.assertTrue(proc is not None)
        self.assertEqual(False, proc.running)
        self.assertTrue(proc.days_to_run is not None)
        self.assertTrue(proc.running_period is not None)

    # Cenario DaysToRun + RunningPeriod
    # Sabado 06:55:00
    @mock_datetime(datetime.datetime(2019, 12, 7, 6, 55, 0))
    def test_DaysToRunAndRunningPeriod_WhenInDaysToRunAndInPeriod_ShouldInitializeTheProcess(self):
        xml_s = '''<?xml version="1.0"?>
        <Primo>
            <Parameters>
                <Parameter name="weekend" value="sun,sat" />
                <Parameter name="tio_log_replay_start_time" value="06:55:00" />
                <Parameter name="tio_log_replay_end_time" value="07:05:00"/>
            </Parameters>

            <Process bin="'''+TEST_PROCESS_PATH+'''" id="tio_log_replay">
                <DaysToRun days="{weekend}" />
                <RunningPeriod start="{tio_log_replay_start_time}" end="{tio_log_replay_end_time}"/>
            </Process>
        </Primo>
        '''

        args = []
        x = primo.XmlConfigParser(args)
        testing_object = x.parse_string(xml_s)

        primo_t = threading.Thread(target=PrimoWorkerFnc, args=(testing_object,))
        primo_t.daemon = True
        primo_t.start()
        primo_t.join(2)

        proc = testing_object.processes['tio_log_replay']

        testing_object.Stop()

        self.assertTrue(proc is not None)
        self.assertEqual(True, proc.running)
        self.assertTrue(proc.days_to_run is not None)
        self.assertTrue(proc.running_period is not None)

    # Cenario RunningPeriod + DaysToRun
    # Segunda
    # DaysToRun tem prioridade
    @mock_datetime(datetime.datetime(2019, 12, 9, 6, 55, 0))
    def test_DaysToRunAndRunningPeriod_WhenNotInDaysToRunAndInPeriod_ShouldNotInitializeTheProcess(self):
        xml_s = '''<?xml version="1.0"?>
        <Primo>
            <Parameters>
                <Parameter name="weekend" value="sun,sat" />
                <Parameter name="tio_log_replay_start_time" value="06:55:00" />
                <Parameter name="tio_log_replay_end_time" value="07:05:00"/>
            </Parameters>

            <Process bin="'''+TEST_PROCESS_PATH+'''" id="tio_log_replay">
                <DaysToRun days="{weekend}" />
                <RunningPeriod start="{tio_log_replay_start_time}" end="{tio_log_replay_end_time}"/>
            </Process>
        </Primo>
        '''

        args = []
        x = primo.XmlConfigParser(args)
        testing_object = x.parse_string(xml_s)

        primo_t = threading.Thread(target=PrimoWorkerFnc, args=(testing_object,))
        primo_t.daemon = True
        primo_t.start()
        primo_t.join(2)

        proc = testing_object.processes['tio_log_replay']

        testing_object.Stop()

        self.assertTrue(proc is not None)
        self.assertEqual(False, proc.running)
        self.assertTrue(proc.days_to_run is not None)
        self.assertTrue(proc.running_period is not None)

    # Cenario RunningPeriod sozinho
    # Segunda
    @mock_datetime(datetime.datetime(2019, 12, 9, 6, 55, 0))
    def test_RunningPeriod_WhenInPeriod_ShouldInitializeTheProcess(self):
        xml_s = '''<?xml version="1.0"?>
        <Primo>
            <Parameters>
                <Parameter name="weekend" value="sun,sat" />
                <Parameter name="tio_log_replay_start_time" value="06:55:00" />
                <Parameter name="tio_log_replay_end_time" value="07:05:00"/>
            </Parameters>

            <Process bin="'''+TEST_PROCESS_PATH+'''" id="tio_log_replay">
                <RunningPeriod start="{tio_log_replay_start_time}" end="{tio_log_replay_end_time}"/>
            </Process>
        </Primo>
        '''

        args = []
        x = primo.XmlConfigParser(args)
        testing_object = x.parse_string(xml_s)

        primo_t = threading.Thread(target=PrimoWorkerFnc, args=(testing_object,))
        primo_t.daemon = True
        primo_t.start()
        primo_t.join(2)

        proc = testing_object.processes['tio_log_replay']

        testing_object.Stop()

        self.assertTrue(proc is not None)
        self.assertEqual(True, proc.running)
        self.assertTrue(proc.running_period is not None)

if __name__ == "__main__":
    unittest.main()
