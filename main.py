#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import math
import codecs
import datetime
import StringIO
import functools
import sae

from os import sys, path
from peewee import *
from flask import Flask, render_template, flash
from flask import request, redirect, url_for, Response
from flask.globals import session
from openpyxl import Workbook

# set default encoding
reload(sys)
sys.setdefaultencoding('utf8')

# seesion secret_key
SECRET_KEY = 'jianglin, secret!'
app = Flask(__name__)
app.config.from_object(__name__)
app.debug = False

# mysql database connection
db = MySQLDatabase(
    user=sae.const.MYSQL_USER,
    passwd=sae.const.MYSQL_PASS,
    host=sae.const.MYSQL_HOST,
    port=int(sae.const.MYSQL_PORT),
    database=sae.const.MYSQL_DB,
    charset='utf8')
    
# pagination setting
# 每页itemInPage个条目，而且导航栏的候选数也最多为itemInPage(懒得改了)
itemInPage = 8

# Database Modals
class BaseModal(Model):
    ''' base Database Model
    all the model use the same database `db`
    '''
    class Meta:
        database = db

class User(BaseModal):
    ''' table `user` '''
    userNo = PrimaryKeyField()
    userId = CharField(128)
    password = CharField(128)
    type = CharField(64)
    
    @classmethod
    def verify(cls, uid, password):
        try:
            user = User.get(User.userId == uid)
        except:
            return None
        if user.password == password:
            return user.type
    
    @classmethod
    def update_account(cls, type, userId, userPasswd):
        User.update(userId=userId, password=userPasswd)\
            .where(User.type == type).execute()
        
class Branch(BaseModal):
    ''' table `branch` '''
    branchNo = PrimaryKeyField()
    branchName = CharField(128)
    branchCate = CharField(64)
    superCate = CharField(64)
    
    @classmethod
    def import_branch(cls):
        '''import branch information from external files
        
        file 'info' is generated from '事业单位'
        file 'info2' is generated from '行政机构'
        two files have different structure
        below program is based on the structure
        '''
        # read file info
        with codecs.open('static/info/info', 'r', 'utf8') as file:
            branch = []
            categorys = []
            lines = file.readlines()  # read file
        
            for line in lines:
                # remove leading and trailing whitespace
                line = line.strip();  
                
                if line.find('#') is not -1:
                    continue
                elif line.find('*') is not -1:
                    m = re.match(r'(.*)[*](\d+)', line)
                    categ = m.group(1)
                    counter = m.group(2)
                    for i in range(int(counter)):
                        categorys.append(categ)
                else:
                    branch.append(line)
        
            # store in database
            for i in range(len(branch)):
                Branch.create(
                    branchName=branch[i],
                    branchCate=categorys[i],
                    superCate='事业单位'
                )
        
        # read file info2
        with codecs.open('static/info/info2', 'r', 'utf8') as file:
            branch = []
            categorys = []
            lines = file.readlines()
            
            for line in lines:
                line = line.strip();
                if line.find('#') is not -1:
                    if categ != line.replace('#', ''):
                        categ = line.replace('#', '')
                else:
                    branch.append(line)
                    categorys.append(categ)
                
            # store in database
            for i in range(len(branch)):
                Branch.create(
                    branchName=branch[i],
                    branchCate=categorys[i],
                    superCate='行政单位'
                )
    
    @classmethod
    def update_branch(cls, branchNo, branchName, branchCate):
        (Branch.update(
                branchName=branchName,
                branchCate=branchCate
            ).where(Branch.branchNo == branchNo)
        ).execute()
        
    @classmethod
    def new_branch(cls, branchName, branchCate, superCate):
        return Branch.create(
            branchName=branchName,
            branchCate=branchCate,
            superCate=superCate
        ).branchNo
        
class Sheet(BaseModal):
    ''' table `sheet`
    
    sheet heads are stored in table `head` 
    sheet data are stored in table `data`
    '''
    
    sheetNo = PrimaryKeyField()
    sheetName = CharField(64)
    releaseTime = DateTimeField(default=datetime.datetime.now, index=True)
    superCate = CharField(64)
    closed = BooleanField(default=False)

    @classmethod
    def new_sheet(cls, sheetName, superCate, theadList):
        # create a new sheet,and get it's number
        sheetNo = Sheet.create(
            sheetName=sheetName,
            superCate=superCate
        ).sheetNo
        
        # create corresponding head
        Head.new_head(sheetNo, theadList)
        return sheetNo
        
class Announce(BaseModal):
    '''table `announce`
    
    each announce will be released with a sheet
    if not, sheetNo will be set as NULL
    '''
    announceNo = PrimaryKeyField()
    title = CharField(64)
    releaseTime = DateTimeField(default=datetime.datetime.now, index=True)
    content = CharField(1024)
    sheetNo = ForeignKeyField(Sheet,
                related_name='sheet2announce',
                to_field='sheetNo',
                on_delete='CASCADE',  # 删除时强制删除关联的外键
                null=True
            )
    
    @classmethod
    def new_announce(cls, title, content,
                sheetName=None, superCate=None, theadList=None):
        
        # judge whether there is a sheet released with the announce
        if theadList:
            # create sheet
            sheetNo = Sheet.new_sheet(sheetName, superCate, theadList)
            # create announce
            Announce.create(
                title=title,
                content=content,
                sheetNo=sheetNo
            )
        else:
            # insert announce record
            Announce.create(title=title, content=content)
    
    @classmethod
    def update_announce(cls, announceNo, title, content,
                sheetName=None, superCate=None, theadList=None):
        '''update announce and sheet(if exists)
        
        if the theadList is not null, then update sheet in the maintime
        '''
        
        # get the announce and update it
        announce = Announce.get(Announce.announceNo == announceNo)
        announce.title = title
        announce.content = content
        announce.save()
        
        # if the sheet need to update
        if theadList:
            (Sheet.update(sheetName=sheetName, superCate=superCate)
                .where(Sheet.sheetNo == announce.sheetNo)
            ).execute()
            Head.update_head(announce.sheetNo, theadList=theadList)
    
    @classmethod
    def delete_announce(cls, announceNo):
        ''' delete announce and sheet(if exists)
        
        if the sheet exists, just delete the sheet can delete records 
        in all the table associated with it, such as announce, head and data
        for those tables are related with Foreign Key
        
        '''
        announce = Announce.get(Announce.announceNo == announceNo)
        sheetNo = announce.sheetNo
        announce.delete_instance(recursive=True)
        
        # delete sheet and dependent objects recursively if it exists 
        if sheetNo:
            Sheet.get(Sheet.sheetNo == sheetNo.sheetNo).delete_instance(recursive=True)
        
class Head(BaseModal):
    ''' table 'head'
    store all the table heads 
    '''
    sheetNo = ForeignKeyField(Sheet,
                related_name='sheet_in_head',
                to_field='sheetNo',
                on_delete='CASCADE'
            )
    headNo = IntegerField()
    head = CharField(64)
    
    class Meta:
        primary_key = CompositeKey('sheetNo', 'headNo')
        
    @classmethod
    def update_head(cls, sheetNo, theadList):
        '''update head when there is no data in sheet
            
        do not use Head.update(),for the number of heads is mutable
        and usually the number of heads won't be more than 15,
        so it will not affect the performance of database
        
        '''
        Head.delete().where(sheetNo == sheetNo).execute()
        Head.new_head(sheetNo, theadList)
    
    @classmethod
    def new_head(cls, sheetNo, theadList):
        # 按照在theadList的顺序分配headNo，从1开始
        for i in range(len(theadList)):
            Head.create(sheetNo=sheetNo, headNo=i + 1, head=theadList[i])
    
    @classmethod
    def get_headMap(cls, sheetNo):
        '''返回SelectQuery,包含headNo和head'''
        return (Head.select(Head.headNo, Head.head).where(Head.sheetNo == sheetNo)
                .distinct(is_distinct=True).order_by(Head.headNo))
        
class Data(BaseModal):
    ''' table `data`
    
    store data in the sheet
    distinguished by sheetNo headNo and branchNo
    '''
    sheetNo = ForeignKeyField(Head,
                related_name='sheet_in_data',
                to_field='sheetNo',
                on_delete='CASCADE'
            )
    headNo = IntegerField()
    branchNo = ForeignKeyField(Branch,
                related_name='branch_in_data',
                to_field='branchNo',
                on_delete='CASCADE'
            )
    data = CharField(128)
    
    class Meta:
        primary_key = CompositeKey('sheetNo', 'headNo', 'branchNo')
    
    @classmethod
    def new_data(cls, sheetNo, branchNo, dataList):
        # 按照在theadList的顺序分配headNo，从1开始
        for i in range(len(dataList)):
            Data.create(sheetNo=sheetNo, headNo=i + 1, branchNo=branchNo, data=dataList[i])
            
    @classmethod
    def update_data(cls, sheetNo, branchNo, dataList):
        for i in range(len(dataList)):
            Data.update(data=dataList[i]).where(
                    Data.sheetNo == sheetNo,
                    Data.headNo == i + 1,
                    Data.branchNo == branchNo).execute()
    
    @classmethod
    def has_data(cls, sheetNo):
        if Data.select().where(Data.sheetNo == sheetNo).count() > 0:
            return True
        
def create_table():
    '''create tables
    
    drop table if it exists and create table if it not exists
    '''
    db.drop_tables([Branch, Announce, Sheet, Head, Data, User], safe=True, cascade=True)
    db.create_tables([Branch, Announce, Sheet, Head, Data, User], safe=True)
    Branch.import_branch()
    User.create(userId='admin', password='guohan', type='admin')
    User.create(userId='user', password='user', type='user')
    User.create(userId='finalize', password='19961020', type='root')

@app.before_request
def before_request():
    db.connect()
    
@app.after_request
def after_request(response):
    db.close()
    return response

# view functions which show their URLs in browser
@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html')

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html')

@app.route('/login/', methods=['POST', 'GET'])
def login():
    uid = request.form.get('uid')
    passwd = request.form.get('passwd')
    type = User.verify(uid, passwd)
    if type != None:
        session[type] = True
        # session.permanent = True  # Use cookie to store session.
        return redirect(url_for(type + '_home'))
    else:
        flash('用户名或密码错误.', 'warning')
        return redirect(url_for('index'))

def login_required(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # 提取函数名，从而判断用户类型
        print re.findall('(\w+)_', func.__name__)[0]
        if session.get(re.findall('(\w+?)_', func.__name__)[0]) != None:
            return func(*args, **kwargs)
        else:
            return redirect(url_for('index'))
    return wrapper

@app.route('/logout/', methods=['GET', 'POST'])
def logout():
    session.clear()
    flash('您已经登出，请重新登录.', 'success')
    return redirect(url_for('index'))

@app.route('/')
def index():
    message = "若页面不能正常显示,说明您的浏览器版本过低。\
        请换用搜狗、猎豹、360急速等基于chrome内核的浏览器；\
        或者使用IE(10、11) firefox(火狐)、chrome(谷歌)，opera(欧朋)浏览器"
    flash(message, 'warning')
    return custom_render('index.html')

@app.route('/admin/home')
@login_required
def admin_home():
    '''home page of administrator'''
    # just use the latest 3 announce
    result = Announce.select().order_by(Announce.releaseTime.desc()).paginate(1, 3)
    return custom_render('admin/home.html', announces=result,)

@app.route('/admin/new')
@login_required
def admin_new():
    '''release a new announcement'''
    return custom_render('admin/new.html')

@app.route('/admin/edit/<announceNo>')
@login_required
def admin_edit(announceNo):
    '''edit an announcement which has been released'''
    
    # check if the index is valid
    try:
        announce = Announce.get(Announce.announceNo == announceNo)
    except Announce.DoesNotExist:
        return redirect(404)
    
    # get sheetNo
    sheetNo = announce.sheetNo
    
    # if there exists a sheet, get extra data from sheet
    if sheetNo:
        sheet = Sheet.get(Sheet.sheetNo == sheetNo)
        heads = (Head.select(Head.headNo, Head.head).where(Head.sheetNo == sheetNo)
                .distinct(is_distinct=True).order_by(Head.headNo))
        hasData = Data.has_data(sheetNo)
    else:
        sheet = heads = hasData = None
    return custom_render('admin/edit.html', announce=announce,
                sheet=sheet, heads=heads, hasData=hasData)

@app.route('/admin/tables/<int:page>')
@login_required
def admin_tables(page=1):
    '''显示所有发布的表格'''
    query = Sheet.select().order_by(Sheet.releaseTime.desc())
    return render_with_page('admin/tables.html', query, 'admin_tables', page)

@app.route('/admin/announce/<int:page>')
@login_required
def admin_announce(page=1):
    '''显示所有发布的公告'''
    query = Announce.select().order_by(Announce.releaseTime.desc())
    return render_with_page('admin/announce.html', query, 'admin_announce', page)

@app.route('/admin/manager/<int:page>')
@login_required
def admin_manager(page=1):
    '''管理成员'''
    query = Branch.select().order_by(Branch.branchNo)
    return render_with_page('admin/manager.html', query, 'admin_manager', page)

@app.route('/admin/account')
@login_required
def admin_account():
    admin = User.get(User.userNo == 1)
    user = User.get(User.userNo == 2)
    return custom_render('admin/account.html', admin=admin, user=user)

@app.route('/admin/sheet/<sheetNo>')
@login_required 
def admin_sheet(sheetNo):
    '''显示单个表格的提交信息'''
    return custom_render('admin/sheet.html', **get_sheet_data(sheetNo))

@app.route('/user/home')
@login_required
def user_home():
    result = Announce.select().order_by(Announce.releaseTime.desc()).paginate(1, 3)
    return custom_render('user/home.html', announces=result,)

@app.route('/user/announce/<int:page>')
@login_required 
def user_announce(page=1):
    query = Announce.select().order_by(Announce.releaseTime.desc())
    return render_with_page('user/announce.html', query, 'user_announce', page)

@app.route('/user/tables/<int:page>')
@login_required
def user_tables(page=1):
    query = Sheet.select().order_by(Sheet.releaseTime.desc())
    return render_with_page('user/tables.html', query, 'user_tables', page)

@app.route('/user/sheet/<sheetNo>')
@login_required
def user_sheet(sheetNo):
    return custom_render('user/sheet.html', highlightNo=request.args.get('highlightNo'), **get_sheet_data(sheetNo))

@app.route('/user/write/<int:sheetNo>')
@login_required
def user_write(sheetNo):
    '''用户填写信息的页面
    
    同过sheetNo获取到branch和data
    并把数据显示在填写页中
    
    若没有data，则说明是初次提交，页面中填入branchName和branchCate即可
    若有data,则说明是更改信息，填入之前所有已填写的信息
    '''
    sheet = Sheet.get(Sheet.sheetNo == sheetNo)
    heads = Head.get_headMap(sheetNo)
    
    # URL合法性验证，自己写的一定会传入branchNo，除非有人瞎搞
    try:
        branch = Branch.get(branchNo=int(request.args.get('branchNo', 0)))
        datas = [data.data for data in Data.select()\
                .where(Data.branchNo == branch.branchNo, Data.sheetNo == sheetNo)]
    except:
        return redirect(404)
    return custom_render('user/write.html', sheet=sheet,
                    branch=branch, heads=heads, datas=datas)

# view functions to manipulate data in database
# they receive data and handle them
# after which they redirect to 
# above view functions to show changes via HTML files

@app.route('/admin/init')
@login_required
def admin_init():
    if request.args.get('init') == '49a99329766fdd5002309c6a225b32472c47bc3e':
        create_table()
        flash('初始化成功,管理员账号admin,密码guohan', 'success')
        return redirect(url_for('index'))
    return custom_render('admin/init.html')

@app.route('/admin/announce/new', methods=['POST'])
@login_required
def admin_announce_new():
    '''发布新公告，处理数据'''

    dataMap = request.form
    announceTitle = dataMap['announceTitle']
    announceContent = dataMap['announceContent']
        
    # 是否发布表格
    releaseSheet = None
    try:
        releaseSheet = dataMap['releaseSheet']
    except:
        pass
        
    # 公告标题或内容不能为空
    if len(re.sub('\s+', '', announceContent)) < 1 or\
        len(re.sub('\s+', '', announceTitle)) < 1:
        
        flash('公告标题、内容不能为空', 'warning')
        return redirect(url_for('admin_new'))
    elif releaseSheet == None:
        # 仅发布公告
        Announce.new_announce(announceTitle, announceContent)
    else:
        # 同时发布表格
        superCate = dataMap['superCate']
        sheetName = dataMap['sheetName']
            
        # 去除空表头,提取`tableHead`,并插入到相应位置
        headsList = extract_form_data(dataMap)
            
        # 不能不填表头或者不写表名称
        if len(headsList) == 2 or len(re.sub('\s+', '', sheetName)) < 1:
            flash('表名、表头不能为空', 'warning')
            return redirect(url_for('admin_new'))
        else:
            Announce.new_announce(announceTitle, announceContent,
                    sheetName, superCate, headsList)
    
    flash('您已成功发布公告', 'success')
    return redirect(url_for('admin_home'))

@app.route('/admin/announce/update/', methods=['POST'])
@login_required
def admin_announce_update():
    '''更新公告，处理数据'''
    
    # 公告数据
    dataMap = request.form
    announceTitle = dataMap['announceTitle']
    announceContent = dataMap['announceContent']
    announceNo = dataMap['announceNo']
        
    # 是否更新表格，更新则为'True',否则为'False'(字符串)
    updateSheet = dataMap['updateSheet']
    
    # 禁止空数据
    if len(re.sub('\s+', '', announceContent)) < 1 or \
        len(re.sub('\s+', '', announceTitle)) < 1:
        
        flash('公告标题、内容不能为空', 'warning')
        return redirect(url_for('admin_edit', announceNo=announceNo))
    elif updateSheet == 'False':
        Announce.update_announce(announceNo, announceTitle, announceContent)
    else:
        # 更新表格
        superCate = dataMap['superCate']
        sheetName = dataMap['sheetName']
        
        # 去除空表头,提取`tableHead`,并插入到相应位置
        headsList = extract_form_data(dataMap)
            
        # 禁止空数据
        if len(headsList) == 2 or len(re.sub('\s+', '', sheetName)) < 1:
            flash('表名、表头不能为空', 'warning')
            return redirect(url_for('admin_edit', announceNo=announceNo))
        else:
            Announce.update_announce(announceNo, announceTitle, announceContent,
                    sheetName, superCate, headsList)
    flash('您已成功更改数据', 'success')
    return redirect(url_for('admin_home'))

@app.route('/admin/announce/delete/<int:announceNo>')
@login_required
def admin_announce_delete(announceNo):
    Announce.delete_announce(announceNo)
    flash('您已成功删除数据', 'success')
    return redirect(url_for('admin_home'))
 
@app.route('/admin/branch-new', methods=['POST'])
@login_required
def admin_branch_new():
    # 创建并获取branchNo
    branchNo = Branch.new_branch(
                branchName=request.form['branchName'],
                branchCate=request.form['branchCate'],
                superCate=request.form['superCate'])
        
    # 找到branch所在页面，标识为高亮
    page = int(math.ceil(float(branchNo) / itemInPage))
    query = Branch.select().order_by(Branch.branchNo)
    return render_with_page('admin/manager.html', query,
                    'admin_manager', page, highlightNo=branchNo)

@app.route('/admin/branch-update/<branchname>', methods=['POST'])
@login_required
def admin_branch_update(branchname):
    # 获取branchNo
    branchNo = request.form['branchNo']
    # 更新成员信息
    Branch.update_branch(branchNo,
            request.form['branchName'],
            request.form['branchCate'])
        
    # 找到branch所在页面，标识为高亮
    page = int(math.ceil(float(branchNo) / itemInPage))
    query = Branch.select().order_by(Branch.branchNo)
    return render_with_page('admin/manager.html', query,
                'admin_manager', page, highlightNo=branchNo)

@app.route('/admin/account/change', methods=['POST'])
@login_required
def admin_account_update():
    dataMap = request.form
    if len(re.sub('\s+', '', dataMap['type'])) > 0 and \
        len(re.sub('\s+', '', dataMap['userId'])) > 0 and \
        len(re.sub('\s+', '', dataMap['userPasswd'])) > 0:
        
        User.update_account(dataMap['type'], dataMap['userId'], dataMap['userPasswd'])
        flash('您已成功更改账号信息', 'success')
        if dataMap['type'] == 'admin':
            return logout()
    else:
        flash('用户名、密码不能为空', 'warning')
    return redirect(url_for('admin_account'))
    
@app.route('/admin/closeTable/<sheetNo>')
@login_required
def admin_sheet_close(sheetNo):
    Sheet.update(closed=True).where(Sheet.sheetNo == sheetNo).execute()
    flash('您已禁止该表格的填报', 'success')
    return redirect(url_for('admin_sheet', sheetNo=sheetNo))

@app.route('/admin/openTable/<sheetNo>')
@login_required
def admin_sheet_open(sheetNo):
    Sheet.update(closed=False).where(Sheet.sheetNo == sheetNo).execute()
    flash('您已开启该表格的填报', 'success')
    return redirect(url_for('admin_sheet', sheetNo=sheetNo))

@app.route('/admin/print/<sheetNo>')
@login_required
def admin_sheet_print(sheetNo):
    # 获取表格对象
    workbook = Workbook()
    worksheet = workbook.active
    
    # 获取表格数据
    dataList = get_sheet_data(sheetNo)
    sheet = dataList['sheet']
    heads = [head.head for head in dataList['heads']]
    datas = dataList['datas']
    
    # 生成表格
#     for i in range(len(heads)):
#         worksheet[chr(65 + i) + str(1)] = heads[i]  # 'A'对应的ASCII码为65
#     for rowNo in range(len(datas)):
#         # 每行，除去末尾的branchNo，详见`get_sheet_data`文档
#         for i in range(len(datas[rowNo]) - 1):  
#             worksheet[chr(65 + i) + str(rowNo + 2)] = datas[rowNo][i]
    
    # 傻逼he，不是有append方法添加一行么
    worksheet.append(heads)
    for data in datas:
        # 每行，除去末尾的branchNo，详见`get_sheet_data`文档
        worksheet.append(data[:len(data) - 1])
        
    # 获取数据流，将其连接至response
    output = StringIO.StringIO()
    workbook.save(output)
    response = Response()
    response.data = output.getvalue()
    
    # 设置相应头
    response.headers["Content-Disposition"] = "attachment; filename=%s.xlsx" % sheet.sheetName
    return response

@app.route('/user/submit/', methods=['POST'])
@login_required
def user_submit():
    '''用户填报或者更改数据'''
    dataMap = request.form
    sheetNo = dataMap['sheetNo']
    
    # 表单中name=1的数据对应branchNo
    branchNo = Branch.get(Branch.branchName == dataMap['1']).branchNo
    # 判断表单中有无空数据
    if '' in dataMap.values():
        flash('各数据值不能为空', 'warning')
        return redirect(url_for('user_write', sheetNo=sheetNo, branchNo=branchNo))
    
    # 提取数据
    dataList = extract_form_data(dataMap)
    
    # 若有`update`信息，则表示更新数据而不是填报
    if request.form.get('update'):
        Data.update_data(sheetNo, branchNo, dataList)
        flash('您已成功更改数据', 'success')
    else:
        Data.new_data(sheetNo, branchNo, dataList)
        flash('您已成功填报数据', 'success')
        
    return redirect(url_for('user_sheet', sheetNo=sheetNo, highlightNo=branchNo))

# utility functions
def extract_form_data(dataMap):
    '''从form获得的参数中获取数据
    
    按照编号由小到大排序，剔除空数据及非表头
    '''
    def find_head(head):
        try:
            int(head)
        except:
            return None
        return int(head)  # 返回int用于排序
    
    return [re.sub('\s+', '', dataMap[str(key)]) for key in \
        sorted(map(find_head, dataMap.keys())) \
        if key and len(dataMap[str(key)].strip()) > 0]
    
def get_sheet_data(sheetNo):
    '''获取指定表格中的所有数据
    
    需要`sheet` `heads` `datas`
    
    sheet根据sheetNo,从Sheet中获得
    heads根据sheetNo,从Head中获得(按照headNo排序)
    最复杂的是datas，datas=((row1),(row2)....)
    
    先提取出所有branch(事业单位或则行政单位)
    然后根据branch找出所有对应的data(按照headNo排序)
    该单位没有提交则为空
    
    return  {'sheet':sheet, 'heads':heads, 'datas':datas}
    `sheet` SelectQuery 
    `heads` SelectQuery 
    `datas` two-dimensional list,每行数据的末尾是其branchNo
    '''
    # 查找sheet
    try:
        sheet = Sheet.get(Sheet.sheetNo == sheetNo)
    except Sheet.DoesNotExist:
        return redirect(404)
    
    # 查找所有head(按照headNo排序)
    heads = Head.get_headMap(sheetNo)
    # 查找该表对应的所有数据
    dataMap = Data.select().where(Data.sheetNo == sheetNo)
    
#     # 查找该表中所有已经提交数据的branchNo
#     branches = (dataMap.select(Data.branchNo)
#             .distinct(is_distinct=True)
#             .order_by(Data.branchNo))
    
    # 查找所有该superCate中的branchNo
    allBranches = (Branch.select()
                .where(Branch.superCate == sheet.superCate)
                .order_by(Branch.branchNo))
    
    # 提取出各个branch对应的数据,未提交则数据只含branchName，branchCate
    datas = []
    for branch in allBranches:
        # 获取branch对应的data
        dataQuery = (dataMap.select()
                .where(Data.branchNo == branch.branchNo)
                .order_by(Data.headNo))
        if dataQuery.count() == 0:
            data = ['' for i in range(heads.count())]
            data[0] = branch.branchName
            data[1] = branch.branchCate
        else:
            data = [dataM.data for dataM in dataQuery]
        # 需要填入branchNo，用于更改与提交数据
        data.append(branch.branchNo)
        datas.append(data)
    
    return {'sheet':sheet, 'heads':heads, 'datas':datas}

def custom_render(*args, **kwds):
    '''装饰render_template
    
    因为部分render_template需要传入最近发布的表格
    '''
    latestSheet = Sheet.select().order_by(Sheet.releaseTime.desc()).paginate(1, 5)
    return render_template(latestSheet=latestSheet, *args, **kwds)

def render_with_page(render_file, query, query_router, page=1, **kwds):
    '''含有分页查询的页面渲染
    
    `render_file` 模板文件
    `query` 传入的经由数据库查询的数据
    `query_router` 分页查询的URL
    `page` 需要显示的页面
    `kwds` 其它需要传入的参数
    
    分页之后的数据命名为`object_lists`
    '''
    
    # 计算总数、判断越界
    sum = query.count()
    if sum > 0 and (page * itemInPage - sum >= itemInPage or page < 1) :  # error
        return redirect(404)
    else:
        return custom_render(render_file,
                object_lists=query.paginate(page, itemInPage),
                thePage=page,
                itemInPage=itemInPage,
                maxItems=sum,
                query_router=query_router,
                 **kwds)
