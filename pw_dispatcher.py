from addon.common.addon import Addon

_1CH = Addon('plugin.video.1channel')
class PW_Dispatcher:
    def __init__(self):
        self.func_registry={}
        self.pos_args_registry={}
        self.kw_args_registry={}

    # call_string MUST be of the format "mode: (positional arguments list) {kw arguments list}"
    # positional argument must be in the order the function expects, kw_arg can be in any order
    # if there are no arguments, just "mode" is sufficient
    def register(self, call_string):
        cleaned_string = call_string.replace(' ','')
        if cleaned_string.find(':')>-1:
            mode,args = cleaned_string.split(':')
        else:
            mode, args = cleaned_string, ''

        def decorator(f):
            if mode in self.func_registry:
                message='Error: %s already registered as %s' % (str(f), mode)
                _1CH.log_error(message)
                raise Exception(message)

            _1CH.log_debug('registering function: |%s|->|%s|' % (mode,str(f)))
            self.func_registry[mode]=f
            _1CH.log_debug('registering args: |%s|-->|%s|' % (mode,args)) 
            pos_args, kw_args = self.__split_arg_string(args, mode)
            self.pos_args_registry[mode]=self.__get_args(pos_args)
            self.kw_args_registry[mode]=self.__get_args(kw_args)
            
            return f
        return decorator

    def __split_arg_string(self, arg_string, mode):
        pos_args=''
        kw_args=''
        if arg_string:
            paren1=arg_string.find('(')
            paren2=arg_string.find(')')
            brace1=arg_string.find('{')
            brace2=arg_string.find('}')
            
            # try to catch some errors - parens or braces out of order, unbalanced parens or braces
            if paren2<paren1 or brace2<brace1 or arg_string.count('(')!=arg_string.count(')') or arg_string.count('{')!=arg_string.count('}'):
                message='Error: Invalid argument string |%s| for mode |%s|' % (arg_string, mode)
                _1CH.log_error(message)
                raise Exception(message)      

            if paren1>=0 and paren2>=0:
                pos_args=arg_string[paren1+1:paren2]
            
            if brace1>=0 and brace2>=0:
                kw_args=arg_string[brace1+1:brace2]
                
        return (pos_args,kw_args)
    
    def __get_args(self, arg_string):
        args=[]
        if arg_string:
            args=arg_string.split(',')
        return args

    def dispatch(self, mode, queries):
        args=[]
        kwargs={}
        if self.pos_args_registry[mode]:
            # positional arguments are all required
            for arg in self.pos_args_registry[mode]:
                if arg in queries:
                    args.append(queries[arg])
                else:
                    message='Error: mode |%s| requested argument |%s| but it was not provided.' % (mode, arg)
                    _1CH.log_error(message)
                    raise Exception(message)
            
        if self.kw_args_registry[mode]:
            #kwargs are optional
            for arg in self.kw_args_registry[mode]:
                if arg in queries:
                    kwargs[arg]=queries[arg]
            
        _1CH.log('Calling |%s| for mode |%s| with pos args |%s| and kwargs |%s|' % (self.func_registry[mode].__name__, mode, args,  kwargs))
        self.func_registry[mode](*args, **kwargs)
