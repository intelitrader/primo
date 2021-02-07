#!/usr/bin/python
# -*- coding: Windows-1252 -*-
import sys
import subprocess
import time
import os
import functools
import traceback
import xml.sax
import time
import calendar
import shlex
import psutil
from heapq import heappop, heappush
from pprint import pprint
from optparse import OptionParser
from datetime import datetime, timedelta
import datetime

if sys.version_info.major == 3:
    from io import StringIO
else:
    from cStringIO import StringIO

if sys.platform == 'win32':
    if sys.version_info.major == 3:
        import winreg as _winreg 
    else:
        import _winreg 

def path_join(a, *args):
    return os.path.join(a, *args)

def SetupCommandLine():
    parser = OptionParser()

    parser.add_option('-d', "--debug", dest="debug", action='store_true', default=False)

    parser.add_option("--parameter", dest="parameters", action='append',
                      help="parameter whose value can be retrivied inside the config file using the ParameterFromCommandLine tag")
    return parser

options, args = SetupCommandLine().parse_args()

def usage():
    print('usage: primo.py [xml config file]')

class CancelEventException(object):
    def __init__(self, who, reason):
        pass

class PropertyParser(object):
     pass

class MemoryInfo:
    virtual_bytes = None
    working_set_bytes = None
    
    def __init__(self, pid):
        p = psutil.Process(pid)
        meminfo = p.memory_info()

        self.virtual_bytes = meminfo.vms        
        self.working_set_bytes = meminfo.rss

        #
        # Para pegar mais propriedades de mem�ria (tipo o uso "real",
        # que o Process Explorer chama de Private bytes) precisamos
        # usar o p.memory_full_info(), que pede mais permiss�es
        # (no macOS, por exemplo, isso d� access denied mesmo para 
        # processos filhos) e � bem mais lenta segundo a documenta��o
        #
    
    def __str__(self):
        return 'virtual=%sMB, working_set=%sMB' % \
            (self.virtual_bytes / (1024*1024),
             self.working_set_bytes / (1024*1024))

    
class Process(object):
    def __init__(self, primo):
        self.bin = None
        self.path = None
        self.cwd = None
        self.pid = None
        self.state = None
        self.properties = {}
        self.event_log = []
        self.command_line_parameters = []
        self.listeners = []
        self.running = False
        self.id = None
        self.disabled = False
        self.days_to_run = None
        self.days_not_to_run = None
        self.running_periods = []
        self.running_period = False
        self.on_specific_time = False

        self.psutils_process = None
            
        self.environ = os.environ        

        #
        # TODO: stdin/stdout *should* be buffered so all listeners can
        # access it
        #
        self.stdout_dst = None
        self.stdin_src = None
        
        self.process_obj = None
        self.primo = primo

    def __repr__(self):
        return '<Process bin=%s path=%s>' % (self.bin, self.path)

    @property
    def thread_count(self):
        return self.psutils_process.num_threads()
    
    @property
    def cpu_percent(self):
        return self.psutils_process.cpu_percent()

    @property
    def start_time(self):
        return time.localtime(self.psutils_process.create_time())

    @property
    def memory_info(self):
        return MemoryInfo(self.pid)

    def add_listener(self, c):
        self.listeners.append(c)

    def setup_stdin(self, stream):
        self.stdin_src = stream

    def setup_stdout(self, stream):
        self.stdout_dst = stream

    def FilePathExists(self):
        bin = path_join(self.path, self.bin)
        return os.path.isfile(bin) and os.access(bin, os.X_OK)

    def StartNow(self):

        if self.running:
            return
        
        bin = path_join(self.path, self.bin)
        if self.disabled:
            print('Process "%s (%s)" is disabled, can\'t StartNow' % (bin, self.id))
            return
        
        args = StringIO()
        args.write(bin)
        args.write(' ')
        for arg in self.command_line_parameters:
            if isinstance(arg, str):
                args.write(arg)
            else:
                args.write(arg(self.primo, self))
                
            args.write(' ')

        _in, _out = None, None
        #
        # In Windows, I got an error trying to write to stdin but not reading the stdout:
        #   File "C:\Python26\lib\subprocess.py", line 761, in _make_inheritable
        #       DUPLICATE_SAME_ACCESS)
        #       WindowsError: (6, 'Invalid identifier')
        #
        if self.stdin_src:
            _in = subprocess.PIPE
            _out = subprocess.PIPE

        if self.stdout_dst:
            _out = subprocess.PIPE
       
        self.primo.raise_process_event('before_start', self, 'after_start_cancel')

        if options.debug:
            print('subprocess:', str(args.getvalue()))

        self.process_obj = subprocess.Popen(shlex.split(str(args.getvalue())), executable=bin, cwd=self.cwd, stdin=_in, stdout=_out, env=self.environ)

        # TODO: everything here is kept in memory during the operation
        # TODO: this will lock primo, should be done in a separated thread
        
        if _in:
            # TODO: we're ignoring stderr
            ret = self.process_obj.communicate(self.stdin_src.read())[0]
            if self.stdout_dst:
                self.stdout_dst.write(ret)
        elif _out:
            while 1:
                ret = self.process_obj.stdout.read()

                if not ret:
                    if self.process_obj.poll() != None:
                        break
                    else:
                        time.sleep(0.5) # TODO: hardcoded timer

                self.stdout_dst.write(ret)

        if self.stdin_src: self.stdin_src.close()
        if self.stdout_dst: self.stdout_dst.close()       
        
        self.pid = self.process_obj.pid
        self.running = self.process_obj.poll() == None

        self.psutils_process = psutil.Process(self.pid)

        self.primo.post_process_event('after_start', self)

        if not self.running:
            self.primo.post_process_event('after_finish', self)

    def KillNow(self):
        if not self.running:
            return
        self.primo.raise_process_event('before_kill', self, 'after_kill_cancel')

        self.process_obj.kill()

        self.running = False        
        
        self.primo.post_process_event('after_kill', self)

    def Start(self):
        return self.primo.schedule_callback(self.StartNow, 0)

    def Kill(self):
        return self.primo.schedule_callback(self.KillNow, 0)            
    
    @property
    def inside_period_to_run(self):
        """Returns True if inside period else False and None to 'I do not know what to do'"""
        # days not to run: priority 1
        if self.days_not_to_run is not None:
            if self.days_not_to_run.inside_period:
                return False

        #days to run + running period: priority 2
        if self.running_period and self.days_to_run:
            for running_period in self.running_periods:
                if running_period.inside_period and self.days_to_run.inside_period:
                    return True
            return False

        # days to run + on specific time: priority 3
        if self.days_to_run and self.on_specific_time:
            return True if self.days_to_run.inside_period else False

        # running period alone: priority 4
        if self.running_period:
            for running_period in self.running_periods:
                if running_period.inside_period:
                    return True
            return False
        
        # on specific time alone: priority 5
        if self.on_specific_time:
            return None

        # days to run alone: priority: 6
        if self.days_to_run:
            return self.days_to_run.inside_period

        return None

class ScheduleCallbackInfo(object):
    def __init__(self, when, callback):
        assert isinstance(when, float) # should be a timestamp like the returned by time.time()
        self.when = when
        self.callback = callback

    def __lt__(self, x):
        return self.when < x.when

    def __le__(self, x):
        return self.when <= x.when

    def __gt__(self, x):
        return self.when > x.when

    def __ge__(self, x):
        return self.when >= x.when

    def __repr__(self):
        t = time.localtime(self.when)
        # showing "callback=<functools.partial object at 0x010596C0>" will not be of much help...
        func = self.callback if not isinstance(self.callback, functools.partial) \
               else '%s %s' % (self.callback.func, self.callback.args)
        return '<ScheduleCallbackInfo: when=%02d:%02d:%02d, callback=%s>' % (t.tm_hour, t.tm_min, t.tm_sec, func)

        
def warn_if_dying(meth):
    def new(*args, **kwargs):
        if args[0].dying: # assuming args[0] is the self param
            print('WARNING: Not supposed to happen when primo is dying.', \
                'Callbacks scheduled when primo is dying will never be executed. Stack: \n"')
            traceback.print_list(traceback.extract_stack())
            
        return meth(*args, **kwargs)

    return new    
'''
class warn_if_dying(object):
    def __init__(self, x):
        self.x = x
    
    def __call__(self, *args, **kwargs):
        if args[0].dying: # assuming args[0] is a primo self
            print 'WARNING: action not supposed to happen when primo is dying: function="%s", params="%s"' \
              % (self.x, args)

        return self.x(*args, **kwargs)
'''

class PrimoStop(Exception):
    def __init__(self):
        pass

class Primo(object):
    def __init__(self):
        self.processes = {}
        self.properties = {}
        self.schedule = []
        self.global_listeners = []
        self.scheduling_log = False
        self.dying = False
        self.initialize_global_listeners()

    def Stop(self):
        self.schedule_callback(self.StopNow, 0)

    def StopNow(self):
        raise PrimoStop()

    def initialize_global_listeners(self):
        self.add_global_listener(FinishMonitorListener)

    #@warn_if_dying
    def add_global_listener(self, listener):
        self.global_listeners.append(listener)

    #@warn_if_dying    
    def add_process(self, process):
        if process.id is None:
            process.id = process.bin + '_' + str(len(self.processes))

        self.processes[process.id] = process

        for c in self.global_listeners:
            process.add_listener(c)

    def schedule_callback_timestamp(self, callback, timestamp):
        info = ScheduleCallbackInfo(timestamp, callback)

        if self.scheduling_log:
            print(info)
            
        heappush(self.schedule, info)
        return id(info)
            
    def schedule_callback(self, callback, delay):
        timestamp = time.time() + delay
        return self.schedule_callback_timestamp(callback, timestamp)
        
    def post_global_event(self, event, delay = 0):
        return self.schedule_callback(
            functools.partial(self.raise_global_event, event),
            delay)

    def post_process_event(self, event, process, delay = 0):
        return self.schedule_callback(
            functools.partial(self.raise_process_event, event, process),
            delay)

    def post_event(self, event, process, callback, delay = 0):
        return self.schedule_callback(
            functools.partial(callback, event, self, process),
            delay)

    def post_event_timestamp(self, event, process, callback, timestamp):
        return self.schedule_callback_timestamp(
            functools.partial(callback, event, self, process),
            timestamp)

    def post_timer_event(self, process, callback, delay):
        return self.post_event('timer', process, callback, delay)

    def post_timer_event_timestamp(self, process, callback, timestamp):
        return self.post_event_timestamp('timer', process, callback, timestamp)    
        
    def raise_global_event(self, event, cancel_event = None):
        for p in self.processes.values():
            self.raise_process_event(event, p, cancel_event)
            
    def raise_process_event(self, event, process, cancel_event = None):
        '''
            listeners must accept three parameters: event, primo, process
        '''        
        for c in process.listeners:
            try:
                c(event, self, process)
            except CancelEventException as ex:
                if cancel_event:
                    try:
                        #
                        # it will not cause a stack overflow because this event can't be cancelled
                        # (hence can't generate more events)
                        #
                        self.raise_process_event(cancel_event, self, p)
                    except Exception as ex:
                        print('unexpected exception calling cancel listeners: %s' % ex)
                        
                    raise # reraise the exception after notifying the cancel
                else:
                    print('callback "%s" is trying to cancel the event "%s", that can\'t be cancelled. Exception: %s' \
                          % (c, event, ex))
                
                
            except Exception as ex:
                print('unexpected exception from callback "%s": %s' % (c, ex))
                
            
    def run(self):
        self.post_global_event('after_attach')

        max_sleep = 5
        self.dying = False
        
        #
        # main loop
        #
        while 1:
            try:
                while self.schedule and self.schedule[0].when < time.time():
                    c = heappop(self.schedule)
                    try:
                        c.callback()
                    except PrimoStop as ex:
                        print('primo.Stop() called')
                        self.dying = True
                        break
                    except Exception as ex:
                        print('exception on main loop: %s' % (repr(ex),))
                    
                if not self.schedule:
                    time.sleep(max_sleep)
                    continue
                
                time_to_next = self.schedule[0].when - time.time()

                if time_to_next <= 0:
                    continue

                time_to_next = min( (time_to_next, max_sleep) )

                time.sleep(time_to_next)                
            except BaseException as ex:
                print('exception on main loop: %s' % (repr(ex),))
                self.dying = True
                break

            if self.dying:
                break


        #
        # MUST be a raise, we're already out of run loop
        #
        self.raise_global_event('before_detach')

'''
    Here for sake of history. You can do all this stuff using RunCodeOnEventListener

def KillOnDetach(event, primo, process):
    if event == 'before_detach':
        process.KillNow()
        
def KeepRunningListener(event, primo, process):
    if event == 'after_finish':
        process.Start()

def AutoStartListener(event, primo, process):
    if event == 'after_attach':
        process.Start()

def LogEventsListener(event, primo, process):
    print 'process "%s", event="%s"' % (process.bin, event)

'''

def FinishMonitorListener(event, primo, process):
    if event == 'after_start':
        primo.post_timer_event(process, FinishMonitorListener, 1) 
        return

    elif event == 'timer':
        if process.process_obj and not process.process_obj.poll() == None:
            process.running = False
            primo.raise_process_event('after_finish', process)
            return

        primo.post_timer_event(process, FinishMonitorListener, 1)

class StringCodeAdapter(object):
    def __init__(self, globals, string_code):
        # it will complain about wrong identation if there are spaces in the beggining
        string_code = string_code.strip(' \t')
        
        self.func = compile(string_code, '<string>', 'exec')
        self.string_code = string_code
        self.globals = globals
        
    def __call__(self, event, primo, process):
        globals = {'event': event, 'primo' : primo, 'process' : process, 'ret' : None}
        if self.globals:
            globals.update(self.globals)
        exec(self.func, globals)
        return globals['ret']

    def __repr__(self):
        return '<StringCodeAdapter string_code="%s">'% self.string_code

class EmbeddedCodeAdapter(object):
    def __init__(self, globals, string_code):
       self.string_code = string_code.strip(' \t')
       self.globals = globals
        
    def __call__(self, primo, process):
        globals = {'primo' : primo, 'process' : process}
        if self.globals:
            globals.update(self.globals)

        ret = ''

        for x in SplitCodeSections(self.string_code):
            if x[0] == '{':
                ret += str(eval(x.strip('{}'), globals))
            else:
                ret += x

        return ret                

    def __repr__(self):
        return '<StringCodeAdapter string_code="%s">'% self.string_code


class ProcessMethodAdapter(object):
    def __init__(self, process_method):
        self.process_method = process_method
        
    def __call__(self, event, primo, process):
        self.process_method(process)

    def __repr__(self):
        return '<ProcessMethodAdapter method="%s">'% self.process_method

class RunCodeOnEventListener(object):
    def __init__(self, event_filter, func):
        self.func = func
        if isinstance(event_filter, str):
            self.event_filter = [str(event_filter)]
        else:
            self.event_filter = event_filter

    def __call__(self, event, primo, process):
        if not self.event_filter or event in self.event_filter:
            return self.func(event, primo, process)

    def __repr__(self):
        return '<RunCodeOnEventListener filter="%s", code="%s">'% (self.event_filter, self.func)

class EachXSecondsListener(object):
    def __init__(self, globals, primo, process, interval, action):
        self.primo = primo
        self.process = process
        self.interval = float(interval)
        self.action = action

        action = action.strip(' {}')
        self.code = StringCodeAdapter(globals, action)
        
        self._schedule()

    def _schedule(self):
        self.primo.post_timer_event(self.process, self, self.interval)

    def __call__(self, action, primo, process):
        #print('EachXSeconds, callback="%s", interval="%0.2f"' % (self.code, self.interval))
        self._schedule()
        self.code('timer', primo, process)

class Days(object):
    WEEKDAYS = {
        'sun': 'Sunday',
        'mon': 'Monday',
        'tu': 'Tuesday',
        'wed': 'Wednesday',
        'th': 'Thursday',
        'fri': 'Friday',
        'sat': 'Saturday'
    }

    def __init__(self, days):
        self.specific_days = []
        self.weekdays = []
        self.days = days

    @property
    def days(self):
        return self.weekdays + self.specific_days
    
    @days.setter
    def days(self, attrs):
        self.weekdays = []
        self.specific_days = []

        days = [day.strip() for day in attrs.split(',')]
        
        for strday in days:
            day = self._parse_days(strday)
            if isinstance(day, str):
                # is weekday
                self.weekdays.append(day)
            else:
                self.specific_days.append(day) 

    def _parse_days(self, day):
        try:
            return datetime.datetime.strptime(day, '%Y-%m-%d').date()
        except ValueError:
            return Days.WEEKDAYS[day]

    @property
    def inside_period(self):
        today = datetime.datetime.today()
        inside_period = (calendar.day_name[today.weekday()] in self.weekdays)
        in_specific_day = (today.date() in self.specific_days)

        if inside_period or in_specific_day:
            return True
        else:
            return False

class DaysToRunListener(object):
    def __init__(self, globals, primo, process):
        self.primo = primo
        self.process = process
        
        self._schedule()

    def __call__(self, action, primo, process):
        today = datetime.datetime.today()

        if self.process.on_specific_time and self.process.inside_period_to_run:
            if self.process.on_specific_time.inside_period:
                self.process.Start()
                return
            else:
                self._schedule()
                return


        if self.process.inside_period_to_run and not self.process.running:
            print('inside days to run period: ', today)
            self.process.Start()

        if self.process.inside_period_to_run == False and self.process.running:
            print('outside days to run period: ', today)
            self.process.KillNow()

        self._schedule()

    def _schedule (self):
        self.primo.post_timer_event(self.process, self, 1)   
  
class RunningPeriod(object):
    def __init__(self, start, end):
        self.start = datetime.datetime.strptime(start, '%H:%M:%S').time()
        self.end = datetime.datetime.strptime(end, '%H:%M:%S').time()
    
    @property
    def inside_period(self):
        today = datetime.datetime.today()
        current_time = datetime.datetime.now().time()

        if self.start < self.end:
            inside_period = (current_time >= self.start and current_time <= self.end)
        else:
            inside_period = (current_time >= self.start or current_time <= self.end)
        
        return inside_period

class RunningPeriodListener(object):
    def __init__(self, globals, primo, process):
        self.primo = primo
        self.process = process
        
        self._schedule()

    def _schedule(self):
        self.primo.post_timer_event(self.process, self, 1)

    def __call__(self, action, primo, process):
        current_time = datetime.datetime.now().time()
        #start = self.process.running_period.start
        #end = self.process.running_period.end
        
        if self.process.inside_period_to_run and not self.process.running:
            print('inside running period: ', current_time)
            self.process.Start()

        if self.process.inside_period_to_run == False and self.process.running:
            print('outside running period: ', current_time)
            self.process.KillNow()

        self._schedule()
        


class OnSpecificTime(object):
    def __init__(self, specific_time):
        self.time = datetime.datetime.strptime(specific_time, '%H:%M:%S').time()

    @property
    def inside_period(self):
        current_time = datetime.datetime.now()

        if self.time.hour == current_time.hour and self.time.minute == current_time.minute:
            if self.time.second > 0:
                if self.time.second == current_time.second:
                    return True
            else:
                return True

        return False


class OnSpecificTimeListener(object):
    def __init__(self, globals, primo, process, time, action):
        self.primo = primo
        self.process = process
        self.time = datetime.datetime.strptime(time, '%H:%M:%S').time()
        self.action = action

        action = action.strip(' {}')
        self.code = StringCodeAdapter(globals, action)
        
        self._schedule()

    def _schedule(self):
        d = datetime.datetime.now()

        # should schedule today or tomorrow?
        if self.time < d.time():
            d += datetime.timedelta(days=1)

        d = datetime.datetime.combine(d.date(), self.time)
        self.datetime = d
        self.primo.schedule_callback_timestamp(self, time.mktime(d.timetuple()))

    def __call__(self):
        if self.process.inside_period_to_run or self.process.inside_period_to_run is None:
            print('OnSpecificTime, callback="%s", datetime="%s"' % (self.code, self.datetime))
            self.code('timer', self.primo, self.process)

            #
            # reschedule. We *assuming* this callback will never be called
            # before the specified time
            #
            now = datetime.datetime.now().time()
            assert(self.time > now)
            self._schedule()

test_xml = \
'''
<Primo>
 <GlobalListeners>
  <EventLogger/>
  <KillOnDetach/>
 </GlobalListeners>
 
 <Process path="c:\windows" bin="notepad.exe">
  <OnEvent event="after_attach" action="{process.Start()}"/>
 </Process>
</Primo>
'''

def SplitCodeSections(s):
    '''
        >>> primo.SplitCodeSections('{lala} abc {123} wer  {xpto}')
        ['{lala}', ' abc ', '{123}', ' wer  ', '{xpto}']
    '''
    ret = []
    cur = 0
    while 1:
        code_start = s.find('{', cur)
        if code_start != -1:
            if cur != code_start:
                ret.append(s[cur:code_start])
            code_end = s.find('}', code_start + 1)
            assert code_end != -1
            ret.append(s[code_start:code_end+1])
            cur = code_end + 1
        else:
            if cur != len(s):
                ret.append(s[cur:])
            break

    return ret
            
            

class XmlConfigParser(xml.sax.handler.ContentHandler):
    def __init__(self, cmdline_params):
        self.element_handlers = {}
        self.element_handlers['Primo'] = self._PrimoElement
        self.element_handlers['GlobalListeners'] = self._GlobalListenersElement
        self.element_handlers['Process'] = self._ProcessElement
        self.element_handlers['OnEvent'] = self._OnEventElement
        self.element_handlers['OnSpecificTime'] = self._OnSpecificTimeElement
        self.element_handlers['RunningPeriod'] = self._RunningPeriod
        self.element_handlers['EachXSeconds'] = self._OnEachXSecondsElement
        self.element_handlers['CommandLineAdd'] = self._CommandLineAddElement
        self.element_handlers['SetEnvironmentVariable'] = self._SetEnvironmentVariable
        self.element_handlers['Parameters'] = self._ParametersElement
        self.element_handlers['StdinFromFile'] = self._StdinFromFile
        self.element_handlers['StdoutToFile'] = self._StdoutToFile
        self.element_handlers['PythonCode'] = self._PythonCode
        self.element_handlers['DaysToRun'] = self._DaysToRun
        self.element_handlers['DaysNotToRun'] = self._DaysNotToRun

        # this will be filled by globals created by code
        # in action and in PythonCode sections
        # The parameters will be inserted to this dict as well
        self.globals = {}
        self.globals['sys'] = sys
        self.globals['os'] = os
        
        self.listeners = {}
        self.cmdline_params = cmdline_params
        
        self.listeners['EventLogger'] = \
            lambda name, attrs: RunCodeOnEventListener(None,
                StringCodeAdapter(self.globals, 'print (\'process "%s", event="%s"\' % (process.bin, event))'))

        self.listeners['KillOnDetach'] = \
            lambda name, attrs: RunCodeOnEventListener('before_detach', ProcessMethodAdapter(Process.KillNow))

        self.listeners['AutoStart'] = \
            lambda name, attrs: RunCodeOnEventListener('after_attach', ProcessMethodAdapter(Process.Start))

        class AutoRestart(object):
            def __init__(self,interval):
                self.interval = interval

            def __call__(self, event, primo, process):
                self.process = process
                self.primo = primo
                self._schedule()

            def _schedule(self):
                self.primo.schedule_callback(self.OnTimer, self.interval)

            def OnTimer(self):
                process = self.process

                self._schedule()                
                
                if process.disabled or process.running:
                    return

                process.Start()
                

        self.listeners['AutoRestart'] = \
            lambda name, attrs: RunCodeOnEventListener('after_attach', AutoRestart(attrs['interval'] if 'interval' in attrs else 1))
        
        self.context_stack = []

        self.primo = None

    def _push_current_handler(self):
        self._push_handler(self.context_stack[-1].handler)
                           
    def _push_handler(self, handler):
        class ElementHandlerInfo:
            pass

        eh = ElementHandlerInfo()
        eh.handler = handler
        self.context_stack.append(eh)
        return eh

    def _pop_handler(self):
        self.context_stack.pop(-1)

    def _call_current_handler(self, name, attrs):
        self.context_stack[-1].handler(name, attrs)

    #
    # Element handlers
    #
    def _StdinFromFile(self, name, attrs):
        process = getattr(self.context_stack[-1], 'process', None)
        assert process

        path = self.EmbeddedCodeProcessor(attrs['path'])
        mode = 'rb'

        f = file(path, mode)
        process.setup_stdin(f)

    def _PythonCode(self, name, attrs):
        pass

    def _StdoutToFile(self, name, attrs):
        process = getattr(self.context_stack[-1], 'process', None)
        assert process

        path = self.EmbeddedCodeProcessor(attrs['path'])        

        # TODO: check invalid modes
        if 'mode' in attrs and attrs['mode'] == 'append':
            mode = 'ab'
        else:
            mode = 'wb'

        f = file(path, mode)
        process.setup_stdout(f)        
                
        
    def _PrimoElement(self, name, attrs):
        self._push_current_handler()

    def _OnSpecificTimeElement(self, name, attrs):
        process = getattr(self.context_stack[-1], 'process', None)

        attrs2 = {}
        # 'action' is always code run on runtime, not on config read
        for key, value in list(attrs.items()):
            attrs2[str(key)] = self.EmbeddedCodeProcessor(value) if key != 'action' else value

        process.on_specific_time = OnSpecificTime(attrs2['time'])
        return OnSpecificTimeListener(
            self.globals,
            self.primo,
            process,
            **attrs2)
    
    def _DaysToRun(self, name, attrs):
        process = getattr(self.context_stack[-1], 'process', None)
        
        days = self.EmbeddedCodeProcessor(attrs['days'])
        days_to_run = Days(days)
        process.days_to_run = days_to_run

        return DaysToRunListener(
            self.globals,
            self.primo,
            process
            )

    def _DaysNotToRun(self, name, attrs):
        process = getattr(self.context_stack[-1], 'process', None)
        days = self.EmbeddedCodeProcessor(attrs['days'])
        days_not_to_run = Days(days)
        process.days_not_to_run = days_not_to_run

    def _RunningPeriod(self, name, attrs):
        process = getattr(self.context_stack[-1], 'process', None)

        start = self.EmbeddedCodeProcessor(attrs['start'])
        end = self.EmbeddedCodeProcessor(attrs['end'])
        running_period = RunningPeriod(start, end)
        process.running_periods.append(running_period)
        process.running_period = True

        return RunningPeriodListener(
            self.globals,
            self.primo,
            process
            )

    def _OnEachXSecondsElement(self, name, attrs):
        process = getattr(self.context_stack[-1], 'process', None)

        attrs2 = {}
        # 'action' is always code run on runtime, not on config read
        for key, value in list(attrs.items()):
            attrs2[str(key)] = self.EmbeddedCodeProcessor(value) if key != 'action' else value
            
        return EachXSecondsListener(
            self.globals,
            self.primo,
            process,
            **attrs2)

    def _ParametersElement(self, name, attrs):
        def add_parameter(name, attrs):
            if name == 'Parameter':
                value = self.EmbeddedCodeProcessor(attrs['value'])
            elif name == 'ParameterFromEnvironment':
                value = os.environ[attrs['varname']] if attrs['varname'] in os.environ else self.EmbeddedCodeProcessor(attrs['default']) if 'default' in attrs else ''
            elif name == 'ParameterFromCommandLine':
                name = attrs['name']
                if name in self.cmdline_params:
                    value = self.cmdline_params[name]
                else:
                    value = attrs['default']
            elif name == 'ParameterFromRegistry':
                if sys.platform == 'win32':
                    k = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, attrs['regkey'])
                    value = _winreg.QueryValueEx(k, attrs['regvalue'])[0]
                    value = _winreg.ExpandEnvironmentStrings(value)
                else:
                    print('WARNING: ParameterFromRegistry tag is support only on Windows, ' + \
                    "for obvious reasons. I\'m *ignoring* it.")
            else:
                # TODO: better error handling
                assert False and 'not a valid parameter element'

            # if it looks like a number, we'll assume it's a number
            parameter_type = attrs['type'] if'type' in attrs else 'string'

            if parameter_type == 'string':
                pass
            elif parameter_type == 'int':
                value = int(value)
            elif parameter_type == 'float':
                value = float(value)
            else:
                raise Exception('Invalid parameter type: ', parameter_type)
            
            # parameters will be added to this dict which is used
            # as "globals" for every code run by primo
            self.globals[self.EmbeddedCodeProcessor(attrs['name'])] = value                
                
                
        self._push_handler(add_parameter)

    def EmbeddedCodeProcessor(self, s):
        eval_globals = {}
        eval_globals['primo'] = self.primo
        eval_globals['process'] = getattr(self.context_stack[-1], 'process', None)
        eval_globals.update(self.globals)

        ret = ''

        for x in SplitCodeSections(s):
            if x[0] == '{':
                ret += str(eval(x.strip('{}'), eval_globals))
            else:
                ret += x

        return ret                

    def _CommandLineAddElement(self, name, attrs):
        process = getattr(self.context_stack[-1], 'process', None)
        assert process
        process.command_line_parameters.append(EmbeddedCodeAdapter(self.globals, attrs['value']))

    def _SetEnvironmentVariable(self, name, attrs):
        process = getattr(self.context_stack[-1], 'process', None)
        assert process
        var_name = self.EmbeddedCodeProcessor(attrs['name'])
        var_value = self.EmbeddedCodeProcessor(attrs['value'])
        process.environ[var_name] = var_value

    def _OnEventElement(self, name, attrs):
        event = attrs['event']
        action = attrs['action']
        action = action.strip('{}')
        return RunCodeOnEventListener(event, StringCodeAdapter(self.globals, action))
        

    def _GlobalListenersElement(self, name, attrs):
        def add_global_listener(name, attrs):
            if name == 'OnEvent':
                listener = self._OnEventElement(name, attrs)
            else:
                listener = self.listeners[name](name, attrs)
                
            self.primo.add_global_listener(listener)

        self._push_handler(add_global_listener)

    def _ProcessElement(self, name, attrs):
        p = Process(self.primo)
        p.path = self.EmbeddedCodeProcessor(attrs['path']) if 'path' in attrs else ''
        p.cwd = self.EmbeddedCodeProcessor(attrs['cwd']) if 'cwd' in attrs else None
        p.bin = self.EmbeddedCodeProcessor(attrs['bin'])
        if 'id' in attrs:
            p.id = self.EmbeddedCodeProcessor(attrs['id'])

        if not p.FilePathExists():
            bin = path_join(p.path, p.bin)
            error = 'Error: File not found: "%s"' % (bin)
            raise Exception(error)

        self.primo.add_process(p)

        def add_process_listener(name, attrs):
            if name == 'OnEvent':
                listener = self._OnEventElement(name, attrs)
            else:
                if name in self.listeners:
                    listener = self.listeners[name](name, attrs)
                else:
                    listener = None
                    self.element_handlers[name](name, attrs)
                    
            if listener:
                p.add_listener(listener)

        eh = self._push_handler(add_process_listener)
        eh.process = p

    def _SimpleElementRouter(self, name, attrs):
        self.element_handlers[name](name, attrs)

    def parse_file(self, file_name):
        try:
            xml.sax.parse(file_name, self)
        except Exception as ex:
            line = self._locator.getLineNumber()
            print('Error on parse file: "%s", at line %s' % (file_name, line))
            raise Exception(ex)
        return self.primo

    def parse_string(self, string):
        xml.sax.parseString(string, self)
        return self.primo

    #
    # SAX handlers
    #

    def startDocument(self):
        self.primo = Primo()
        self._push_handler(self._SimpleElementRouter)

    def endElement(self, name):
        if self.python_code:
            code = self.current_python_code.strip('\t \r\n')

            #
            # The code will be executed now, so it'll probably be used
            # define variables and functions, and not to run any code
            #
            exec(code, self.globals)
            
            self.python_code = False
            self.current_python_code = ''
            
        self._pop_handler()
        
    def startElement(self, name, attrs):
        x = len(self.context_stack)

        # TODO: this is ugly UGLY **** UGLY ***
        self.python_code = (name == 'PythonCode')

        if self.python_code:
            self.current_python_code = ''
        
        self._call_current_handler(name, attrs)

        if len(self.context_stack) == x:        
            self._push_handler(self._not_supposed_to_have_children)

    def characters(self, content):
        if self.python_code:
            self.current_python_code += content

    def _not_supposed_to_have_children(self, name, attrs):
        assert False

    
def Test():
    primo = Primo()
    p = Process(primo)

    primo.add_global_listener(FinishMonitorListener)    

    # auto start and relauch always
    primo.add_global_listener(
        RunCodeOnEventListener(['after_attach', 'after_finish'],
            ProcessMethodAdapter(Process.Start)))

    # log all events
    primo.add_global_listener(
        RunCodeOnEventListener(None,
            StringCodeAdapter(globals(), 'print (\'process "%s", event="%s"\' % (process.bin, event))')))

    # kill on detach
    primo.add_global_listener(
        RunCodeOnEventListener('before_detach',
                             ProcessMethodAdapter(Process.KillNow)))

    p.path = 'c:\\windows'
    p.bin = 'notepad.exe'

    primo.add_process(p)

    primo.run()

def main():
    if len(sys.argv) < 2:
        usage()
        return

    #
    # option must respect syntax name=value, like
    # primo.py test.xml --parameter xpto=10 --parameter foo=bar
    #
    if options.parameters:
        cmdline_params = dict([x.split('=') for x in options.parameters])
    else:
        cmdline_params = {}
    
    x = XmlConfigParser(cmdline_params)
    primo = x.parse_file(sys.argv[1])

    if options.debug:
        for id, p in primo.processes.items():
            print(pprint( (id, p, p.listeners, p.command_line_parameters) ))

    print('running...')
    primo.run()    

if __name__ == '__main__':
    main()
