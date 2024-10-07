# -*- coding: utf-8 -*-
# Copyright (c) 2018, info@valiantsystems.com and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import json
import os
import urllib.parse
from frappe.utils import encode, get_files_path , getdate, to_timedelta,  flt
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.utils.password import encrypt
from go1_cms.go1_cms.api import get_business_from_login, check_domain, get_today_date
from go1_cms.go1_cms.api import get_template_folder, unescape
from urllib.parse import urljoin, unquote, urlencode
from frappe.query_builder import DocType, Field, Order
from frappe.query_builder.functions import Function, Max
from go1_cms.utils.setup import get_settings_from_domain, get_business_from_web_domain

class PageSection(Document):
	 
	def validate(self):
		# getting field information of the selected doctype
		if self.section_type == 'Custom Section' and self.content_type == 'Dynamic':
			fields = []
			if self.fetch_product:
				fields = ["name", "price", "old_price", "short_description", "full_description", "sku", "route", "enable_preorder_product","weight","gross_weight",
					"inventory_method", "minimum_order_qty", "maximum_order_qty", "stock", "disable_add_to_cart_button",
					"image", "thumbnail", "product_brand", "item", "custom_entered_price"]
			else:
				if self.reference_document == 'Product Brand':
					fields = ["brand_name", "route", "brand_logo"]
				elif self.reference_document == 'Product Category':
					fields = ["category_name", "category_image", "menu_image", "mobile_image", "route"]
				elif self.reference_document == 'Subscription Plan':
					fields = ["name", "price"]
			self.field_list = json.dumps(fields)
		elif self.section_type in ['Slider', 'Slider With Banner']:
			fields = ["web_image", "mobile_app_image", "mobile_image", "title", "sub_title", "button_text", "redirect_url"]
			self.field_list = json.dumps(fields)

		if not self.section_type == 'Predefined Section':
			self.is_login_required = 0
		self.context = "data"+self.name.lower().replace('-','')
		self.generate_route()
		cms_settings=get_settings_from_domain("CMS Settings", business=self.business)
		enable_generate_html=cms_settings.generate_html
		if enable_generate_html:
			generate_section_html(self.name)
		self.check_content_fields()

	def check_content_fields(self):
		if self.content:
			for item in self.content:
				if item.field_label and not item.field_key:
					item.field_key = item.field_label.lower().replace(' ', '_')
					check_existing = list(filter(lambda x: (x.field_key == item.field_key and x.name != item.name), self.content))
					if check_existing:
						item.field_key = item.field_key + '_{0}'.format(len(check_existing))

	def generate_route(self):
		if self.section_type not in ['Slider', 'Slider With Banner']:
			if not self.route:
				encrypted = encrypt(self.name)
				url = 'offers-list'
				if self.reference_document and (self.reference_document == 'Product' or self.fetch_product == 1):
					url = 'products-list'
				self.route = '/{0}?token={1}'.format(url, encrypted)

			if self.content:
				for item in self.content:
					if item.get('field_key') == 'view_all_route' and not item.content:
						item.content = self.route

	def on_update(self):
		#created by boopathy
		if not self.class_name:
			
			self.class_name = get_class_name()
			self.save()

		#end

		# pages = frappe.db.sql('''select distinct parent from `tabMobile Page Section` where section = %(section)s and parenttype="Web Page Builder"''',{'section': self.name}, as_dict=1)
		mobile_page_section = DocType('Mobile Page Section')
		pages = (
			frappe.qb.from_(mobile_page_section)
			.distinct()
			.select(mobile_page_section.parent)
			.where(mobile_page_section.section == self.name)
			.where(mobile_page_section.parenttype == "Web Page Builder")
		).run(as_dict=True)
		if pages:
			for item in pages:
				doc = frappe.get_doc('Web Page Builder', item.parent)
				doc.run_method('validate')

	
	def section_data(self, customer=None, add_info=None,store_business=None):
		json_obj = {}
		json_obj['section'] = self.name
		json_obj['class_name'] = self.class_name
		json_obj['section_name'] = self.section_title
		json_obj['section_type'] = self.section_type
		json_obj['content_type'] = self.content_type
		json_obj['reference_document'] = self.reference_document
		json_obj['no_of_records'] = self.no_of_records
		json_obj['view_type'] = self.view_type
		json_obj['view_more_redirect_to'] = self.view_more_redirect_to
		json_obj['mobile_app_template'] = self.mobile_app_template
		json_obj['login_required'] = self.is_login_required
		json_obj['dynamic_data'] = self.dynamic_data
		json_obj['is_full_width'] = self.is_full_width
		json_obj['layout_json'] = self.layout_json
		businesss = ''
		if 'ecommerce_business_store' in frappe.get_installed_apps():
			if self.business:
				businesss = self.business
		if self.section_type == 'Predefined Section' and not self.is_login_required:
			if self.predefined_section=="Recommended Items":
				# frappe.log_error("rec", "recommended")
				json_obj['data'] = get_recommended_products(self.query, self.reference_document, self.no_of_records, business=businesss, customer=customer, add_info=add_info,store_business=store_business)
				json_obj['reference_document'] = self.reference_document
			else:
				json_obj['data'] = get_data_source(self.query, self.reference_document, self.no_of_records, business=businesss, customer=customer, add_info=add_info,store_business=store_business)
				json_obj['reference_document'] = self.reference_document
		elif self.section_type in ['Slider', 'Slider With Banner']:
			slider_cond = ''
			if businesss:
				slider_cond = ' and business = "{0}"'.format(self.business)
			if check_domain("multi_store") and not store_business:
				multi_store_business = frappe.request.cookies.get('selected_store')
				if not multi_store_business:
					all_locations = frappe.db.get_all("Business",fields=['name','restaurant_name'],order_by="is_default desc")
					if all_locations:
						multi_store_business = all_locations[0].name
				else:
					multi_store_business = unquote(frappe.request.cookies.get('selected_store'))
				if multi_store_business:		
					slider_cond = ' and business = "{0}"'.format(multi_store_business)
			if check_domain("multi_store"):
				if store_business:
					cond = (slider.business == store_business) 
			slider = DocType('Slider')
			json_obj['data'] = (
				frappe.qb.from_(slider)
				.select(
					slider.business,
					slider.mobile_app_image,
					slider.mobile_app_videoyoutube_id,
					slider.mobile_image,
					slider.mobile_videoyoutube_id,
					slider.redirect_url,
					slider.slider_type,
					slider.upload_video_for_mobile,
					slider.upload_video_for_mobile_app,
					slider.upload_video_for_web,
					slider.video_type,
					slider.web_image,
					slider.web_videoyoutube_id
				)
				.where(slider.published == 1)
				.where(cond) 
				.orderby(slider.display_order)
			).run(as_dict=True)
			# json_obj['data'] = frappe.db.sql('''select business,mobile_app_image,mobile_app_videoyoutube_id,mobile_image,mobile_videoyoutube_id,redirect_url,slider_type,upload_video_for_mobile,upload_video_for_mobile_app,upload_video_for_web,video_type,web_image,web_videoyoutube_id from `tabSlider` where published = 1 {cond} order by display_order'''.format(cond=slider_cond), as_dict=1)
		elif self.section_type == 'Custom Section':
			
			if self.content_type == 'Static':
				if self.reference_document == 'Product Category':
					json_obj['route'] = frappe.db.get_value(self.reference_document, self.reference_name, "route")
				json_obj['data'] = json.loads(self.custom_section_data)
			else:
				if self.reference_document == 'Product Category' and self.dynamic_data==0:
					json_obj['data'] = json.loads(self.custom_section_data)
				else:
					json_obj['reference_document'] = self.reference_document
					json_obj['reference_name'] = self.reference_name
					json_obj['data'] = get_dynamic_data_source(self, customer=customer,store_business=store_business)
					json_obj['fetch_product'] = self.fetch_product
					if len(json_obj['data']) > 0 and self.reference_name:
						field = None
						if self.reference_document == 'Product Category':
							field = 'category_name'
						if self.reference_document == 'Product Brand':
							field = 'brand_name'
						if self.reference_document == 'Subscription Plan':
							field = 'name'
						if self.reference_document == 'Author':
							field = 'name'
						if self.reference_document == 'Publisher':
							field = 'name'
						if field:
							json_obj['title'] = frappe.db.get_value(self.reference_document, self.reference_name, field)
							if self.reference_document == 'Product Category':
								json_obj['route'] = frappe.db.get_value(self.reference_document, self.reference_name, "route")
		
		elif self.section_type == 'Tabs' and self.reference_document == 'Custom Query':
			if self.reference_document == 'Custom Query':
				data = json.loads(self.custom_section_data)
				for item in data:
					no_of_records = 10
					if item.get('no_of_records'):
						no_of_records = item.get('no_of_records')
					item['name'] = item.get('tab_item').lower().replace(' ', '_')
					query_item = frappe.db.get_value(self.reference_document, item.get('tab_item'), 'query')
					query='''{query} limit {limit}'''.format(query=query_item,limit=no_of_records)
					filters = {}
					if businesss:
						filters = {"business":self.business}
					result = frappe.db.sql(query, filters, as_dict=1)
					result = get_product_details(result, customer=customer)
					item['products'] = result
					org_datas = []
					org_datas = get_products_json(result)
					item['products'] = org_datas
				json_obj['data'] = data

		elif self.section_type == 'Lists':
			if 'erp_go1_cms' in frappe.get_installed_apps():
				from erp_go1_cms.erp_go1_cms.page_section import get_list_data
				json_obj['data'] = get_list_data(self, customer=None, add_info=None,store_business=None)

		
		if self.content:
			for item in self.content:
				if item.field_type != 'List':
					json_obj[item.field_key] = item.content
				else:
					json_obj[item.field_key] = json.loads(item.content) if item.content else []

		return json_obj

	def validate_sql_condition(self):
		if self.condition == '':
			return False
		if self.condition.find(';') > -1:
			return False
		if self.condition.find('update') > -1:
			return False
		if self.condition.find('delete') > -1:
			return False

		return True
def get_products_json(data):
	org_datas = []
	for product in data:
		product_attributes = []
		for x in product.get("product_attributes"):
			options = []
			for option in x.get("options"):
				options.append({
					"attr_itemprice": option.get("attr_itemprice"),
					"attr_oldprice":option.get("attr_oldprice"),
					"is_pre_selected": option.get("is_pre_selected"),
					"name": option.get("name"),
					"option_value": option.get("option_value"),
					"price_adjustment": option.get("price_adjustment"),
					"product_title": option.get("product_title"),
					})
			product_attributes.append({
				"attribute":x.get("attribute"),
				"attribute_unique_name":x.get("attribute_unique_name"),
				"control_type":x.get("control_type"),
				"is_required":x.get("is_required"),
				"name":x.get("name"),
				"options":options
				})
		org_datas.append({
			"image": product.get("image"),
			"image_type":product.get("image_type"),
			"actual_old_price":product.get("actual_old_price"),
			"actual_price": product.get("actual_price"),
			"attribute_old_price": product.get("attribute_old_price"),
			"attribute_price":product.get("attribute_price"),
			"brand_route": product.get("brand_route"),
			"disable_add_to_cart_button": product.get("disable_add_to_cart_button"),
			"discount_percentage": product.get("discount_percentage"),
			"enable_preorder_product": product.get("enable_preorder_product"),
			"has_attr_stock": product.get("has_attr_stock"),
			"have_attribute": product.get("have_attribute"),
			"inventory_method":product.get("inventory_method"),
			"item": product.get("item"),
			"item_title": product.get("item_title"),
			"maximum_order_qty": product.get("maximum_order_qty"),
			"minimum_order_qty": product.get("minimum_order_qty"),
			"name": product.get("name"),
			"old_price": product.get("old_price"),
			"price":product.get("price"),
			"product_attributes":product_attributes,
			"product_brand": product.get("product_brand"),
			"product_image": product.get("product_image"),
			"rating":product.get("rating"),
			"review_count": product.get("review_count"),
			"route": product.get("route"),
			"short_description":product.get("short_description"),
			"sku": product.get("sku"),
			"stock": product.get("stock"),
			"thumbnail": product.get("thumbnail"),
			"weight": product.get("weight"),
			"gross_weight": product.get("gross_weight"),
			"show_attributes_inlist":product.get("show_attributes_inlist"),
			"variant_price": product.get("variant_price")

		})
	return org_datas

def get_data_source(query, dt=None, no_of_records=0, login_required=0, customer=None, user=None, business=None, 
	latitude=None, longitude=None, order_type=None, page_no=0, add_info=None,store_business=None):
	if no_of_records > 0:
		start = int(page_no) * int(no_of_records)
		query = '{0} limit {1},{2}'.format(query, start, no_of_records)
	if not business:
		business = get_business_from_login()
	if check_domain("multi_store") and not store_business:
		multi_store_business = frappe.request.cookies.get('selected_store')
		if not multi_store_business:
			all_locations = frappe.db.get_all("Business",fields=['name','restaurant_name'],order_by="is_default desc")
			if all_locations:
				multi_store_business = all_locations[0].name
		else:
			multi_store_business = unquote(frappe.request.cookies.get('selected_store'))
		if multi_store_business:		
			query = query.replace('where p.is_active','where  p.restaurant = "{0}" AND p.is_active '.format(multi_store_business))
			query  = query.replace('where parent_product_category is null and','where  parent_product_category is null and business = "{0}" AND '.format(multi_store_business))
	
	domain = frappe.get_request_header('host')
	business = get_business_from_web_domain(domain)
	if business:
		query = query.replace('where p.is_active','where  p.restaurant = "{0}" AND p.is_active '.format(business))

	# if check_domain("multi_store"):
	# 	if frappe.request.cookies.get('selected_store'):
	# 		query = query.replace('where p.is_active','where  p.restaurant = "{0}" AND p.is_active '.format(unquote(frappe.request.cookies.get('selected_store'))))
	filters = {}
	filters['business'] = business
	filters['restaurant'] = business
	if latitude:
		filters['latitude'] = latitude
	if longitude:
		filters['longitude'] = longitude
	if login_required:
		if not customer:
			customer = urllib.parse.unquote(frappe.request.cookies.get('customer_id')) if frappe.request.cookies.get('customer_id') else None
		if not user:
			user = frappe.session.user
		filters['customer'] = customer
		filters['user'] = user
	if add_info:
		for k, v in add_info.items():
			filters[k] = urllib.parse.unquote(v)
			if k == 'searchText' or k == 'searchTxt':
				filters[k] = urllib.parse.unquote(v) + '%'
	try:
		result = frappe.db.sql('''{query}'''.format(query=query), filters, as_dict=1)
		if result and dt == 'Product':
			result = get_product_details(result)
		
		return result
	except Exception as e:
		frappe.log_error(frappe.get_traceback(),"go1_cms.cms.doctype.page_section.page_section.get_data_source")
		return []

def get_recommended_products(query=None, dt=None, no_of_records=0, login_required=0, customer=None, user=None, business=None, 
	latitude=None, longitude=None, order_type=None, page_no=0, add_info=None,store_business=None):
	catalog_settings = None
	if 'erp_go1_cms' in frappe.get_installed_apps():
		from erp_go1_cms.utils.setup import get_settings_from_domain
		catalog_settings = get_settings_from_domain('Catalog Settings')
	if 'go1_cms' in frappe.get_installed_apps():
		from go1_cms.utils.setup import get_settings_from_domain
		catalog_settings = get_settings_from_domain('Catalog Settings')
	if catalog_settings:
		recommended_products = []
		recommended_item_list = ""
		if catalog_settings.enable_recommended_products:
			viewed_items = []
			# frappe.log_error(customer, "---customer--rec-")
			if customer:
				customer_viewed_product = DocType('Customer Viewed Product')
				viewed_items = (
					frappe.qb.from_(customer_viewed_product)
					.distinct()
					.select(customer_viewed_product.product)
					.where(customer_viewed_product.parent == customer)  # Replace customer dynamically
				).run(as_dict=True)
				order = DocType('Order')
				order_item = DocType('Order Item')
				order_items = (
					frappe.qb.from_(order)
					.join(order_item)
					.on(order_item.parent == order.name)
					.select(Max(order_item.item).as_('product'))
					.where(order.customer == customer)
				).run(as_dict=True)
				shopping_cart = DocType('Shopping Cart')
				cart_items_table = DocType('Cart Items')
				cart_items = (
					frappe.qb.from_(shopping_cart)
					.join(cart_items_table)
					.on(cart_items_table.parent == shopping_cart.name)
					.select(cart_items_table.product, cart_items_table.price)
					.where(shopping_cart.customer == customer) 
				).run(as_dict=True)
				# frappe.log_error(cart_items, "cart_items")
				for n in cart_items:
					order_items.append(n)
				for s in viewed_items:
					order_items.append(s)
				for s in order_items:
					s.price = frappe.db.get_value("Product", s.product, "price")
				if not order_items:
					order_items = []
				
			else:
				cond = ""
			
				order_item = DocType('Order Item')
				order_items = (
					frappe.qb.from_(order)
					.join(order_item)
					.on(order_item.parent == order.name)
					.select(Max(order_item.item).as_('product'))
				)
				if cond:
					order_items = order_items.where(cond)

				# Execute the query
				order_items = order_items.run(as_dict=True)
				# frappe.log_error(order_items, "order_items")
				for s in order_items:
					s.price = frappe.db.get_value("Product", s.product, "price")
				if not order_items:
					order_items = []
			recommended_item_list = [x.product for x in order_items if x.product]
			product_category_mapping = DocType('Product Category Mapping')
			cat_query = (
				frappe.qb.from_(product_category_mapping)
				.select(product_category_mapping.category)
				.distinct()
				)
			if recommended_item_list:
				cat_query = cat_query.where(product_category_mapping.parent.isin(recommended_item_list))

			cat_items = cat_query.run(as_dict=True)
			max_val = max(flt(node.price) for node in order_items)
			min_val = min(flt(node.price) for node in order_items)
			category_list = []
			category_list=",".join(['"' + x.category + '"' for x in cat_items])
			category_list_values = [x.category for x in cat_items]
			product = DocType('Product')
			product_category_mapping = DocType('Product Category Mapping')
			product_image = DocType('Product Image')
			if category_list:
				subquery = (
					frappe.qb.from_(product_image)
					.select(product_image.list_image)
					.where(product_image.parent == product.name)
					.orderby(product_image.is_primary.desc())
					.limit(1)
				)
				ord_query = (
					frappe.qb.from_(product)
					.select(
						product.start,
						subquery.as_("product_image")
					)
					.inner_join(product_category_mapping).on(product_category_mapping.parent == product.name)
					.where(
						product_category_mapping.category.isin(category_list_values), 
						product.price >= min_val,
						product.price <= max_val
					)
					.limit(no_of_records).offset(1)
				)
				products = ord_query.run(as_dict=True)
			else:
				
				subquery = (
					frappe.qb.from_(product_image)
					.select(product_image.list_image)
					.where(product_image.parent == product.name)
					.orderby(product_image.is_primary.desc())
					.limit(1)
				)
				ord_query = (
					frappe.qb.from_(product)
					.select(
						product.start,
						subquery.as_("product_image")
					)
					.inner_join(product_category_mapping).on(product_category_mapping.parent == product.name)
					.where(
						product.price >= min_val,
						product.price <= max_val
					)
					.limit(no_of_records) 
				)
				products = ord_query.run(as_dict=True)
			
			res_data = get_product_details(products)
			# frappe.log_error(res_data, "res_data")
			if res_data:
				recommended_products = res_data
		return recommended_products
	return []


def get_dynamic_data_source(doc, customer=None,store_business=None):
	result = []
	condition = ""
	business = None
	if not business:
		business = get_business_from_login()
	# if doc.condition: condition = ' and {0}'.format(doc.condition)

	fields = '*'
	if business:
		condition += ' and business = "{0}"'.format(business)
	
	
	doctype = DocType(doc.reference_document)
	query = (
		frappe.qb.from_(doctype).as_("doc")  
	)
	fields_to_select = [field for field in fields.split(",")]  
	query = query.select(*fields_to_select)
	
	domain = frappe.get_request_header('host')
	business = get_business_from_web_domain(domain)
	if business:
		query = query.where(doctype.business==business)
	# if condition:
	# 	query = query.where(condition)
	if doc.reference_document not in ["Product Category", "Product Brand", "Subscription Plan"]:
		query = query.where(doctype.name != "")
	sort_field = doc.sort_field or 'name'  
	# query = query.order_by(getattr(doctype, sort_field), order=doc.sort_by) 
	field = getattr(doctype, sort_field)
	query = query.orderby(field) if doc.sort_by == 'asc' else query.orderby(field, order=Order.desc)
	limit = doc.no_of_records
	query = query.limit(limit)
	result = query.run(as_dict=True)
	return result

@frappe.whitelist()
def get_item_info(dt, dn):
	doc = frappe.get_doc(dt, dn)
	meta = frappe.get_meta(dt)
	title_value = ''
	if meta.title_field:
		title_value = doc.get(meta.title_field)
	else:
		title_value = doc.name
	images = []
	if dt == 'Product':
		product_image = DocType('Product Image')
		images = (
			frappe.qb.from_(product_image)
			.select(
				product_image.list_image,
				product_image.detail_thumbnail.as_("thumbnail") 
			)
			.where(product_image.parent == dn)
			.orderby(product_image.idx) 
		).run(as_dict=True)
	else:
		fields = filter(lambda x: x.fieldtype in ['Attach', 'Attach Image'], meta.fields)
		for item in fields:
			if doc.get(item.fieldname):
				images.append({'thumbnail': doc.get(item.fieldname)})
	return {'title': title_value, 'images': images}

@frappe.whitelist()
def update_page_sections():
	# doc_list = frappe.db.sql('''select name from `tabPage Section` where section_type <> "Banner" or (section_type = "Custom Section" and content_type = "Dynamic")''', as_dict=1)
	page_section = DocType('Page Section')
	doc_list = (
		frappe.qb.from_(page_section)
		.select(page_section.name)
		.where(
			(page_section.section_type != "Banner") | 
			((page_section.section_type == "Custom Section") & (page_section.content_type == "Dynamic"))  
		)
	).run(as_dict=True)
	if doc_list:
		for item in doc_list:
			doc = frappe.get_doc('Page Section', item.name)
			doc.save(ignore_permissions=True)

@frappe.whitelist()
def save_as_template(section, title):
	doc = get_mapped_doc("Page Section", section, {
		"Page Section": {
			"doctype": "Section Template"
		},
		"Section Content":{
			"doctype": "Section Content"
		}
	}, None, ignore_permissions=True)
	doc.name = title
	doc.save(ignore_permissions=True)
	return doc

@frappe.whitelist()
def get_section_template(section):
	return frappe.get_doc('Section Template', section)

def get_section_data(section, customer=None):
	mobile_page_section = DocType('Mobile Page Section')
	section_data = (
	    frappe.qb.from_(mobile_page_section)
	    .select(
	        mobile_page_section.section,
	        mobile_page_section.parent,
	        mobile_page_section.parentfield
	    )
	    .where(mobile_page_section.section == section) 
	).run(as_dict=True)
	data_source = None
	if section_data:
		path = 'data_source/{0}_{1}.json'.format(section_data[0].parent.lower().replace(' ', '_'), ('web' if section_data[0].parentfield == 'web_section' else 'mobile'))
		origin = get_files_path()
		file_path = os.path.join(origin, path)
		if os.path.exists(file_path):
			with open(file_path) as f:
				data = json.loads(f.read())
				data_source = next((x for x in data if x.get('section') == section), None)
				if data_source['login_required'] == 1 and (frappe.session.user != 'Guest' or customer):
					doc = frappe.get_doc('Page Section', section)
					data_source['data'] = get_data_source(doc.query, doc.reference_document, doc.no_of_records, 1, customer)
				if data_source['dynamic_data'] == 1:
					if data_source['section_type'] in ['Predefined Section', 'Custom Section', 'Lists', 'Tabs']:
						doc = frappe.get_doc('Page Section', data_source['section'])
						data_source = doc.run_method('section_data')
	return data_source

#by siva
def generate_section_html(section, view_type=None, content_type="Dynamic"):
	if content_type=="Static":
		generate_static_section(section)

	if content_type=="Dynamic":
		generate_dynamic_section(section, view_type)

def generate_static_section(section):
	context={}
	template = ""
	business=None
	product_template = frappe.db.get_value("Page Section", section, ["name", "business", "section_title", "web_template", "custom_css", "custom_js"], as_dict=True)	
	if product_template:
		if product_template.business:
			business=product_template.business
		data_source = get_section_data(section)
		template = product_template.web_template
		if product_template.custom_css:
			template += '\n <style> \n'  + product_template.custom_css + '\n </style>\n'
		if product_template.custom_js:
			template += '\n{% block script %}\n <script> \n'  + product_template.custom_js + '\n </script>\n{% endblock %}\n'
		template=frappe.render_template(template, {
			'data_source': data_source,
			'currency': frappe.cache().hget('currency', 'symbol')
			})
		temp_path = get_template_folder(business=business)
		html_page = product_template.section_title.lower().replace(' ','-') + "-" + (product_template.name).lower().replace(' ','-')
		with open(os.path.join(temp_path, (html_page+'.html')), "w") as f:
			temp = unescape(encode(template))
			f.write(temp)

def generate_dynamic_section(section, view_type):	
	template = ""
	business=None
	# hide by gopi on 20/10/22
	# product_template = frappe.db.get_value("Page Section", section, ["name", "business","section_title", "web_template", "mobile_view_template", "custom_css", "custom_js"], as_dict=True)	
	product_template = frappe.db.get_value("Page Section", section, ["name","section_title", "web_template", "mobile_view_template", "custom_css", "custom_js"], as_dict=True)	
	# end
	if product_template:
		#context={}
		#content = frappe.db.get_all("Section Content", fields=["*"], filters={"parent":product_template.name})
		#for con in content:
		#	context[con.field_key]=con.content
		if product_template.business:
			business=product_template.business
		if product_template.web_template:
			template += product_template.web_template
		if product_template.mobile_view_template:
			template +=product_template.mobile_view_template
		if not template:
			template = ''
		if product_template.custom_css:
			template += '\n <style> \n'  + str(product_template.custom_css or '') + '\n </style>\n'
		if product_template.custom_js:
			template += '\n <script> \n'  + str(product_template.custom_js or '') + '\n </script>\n'
		temp_path = get_template_folder(business=business)
		html_page = product_template.section_title.lower().replace(' ','-') + "-" + (product_template.name).lower().replace(' ','-')
		with open(os.path.join(temp_path, (html_page+'.html')), "w") as f:
			#temp = unescape(encode(template))
			temp = template
			f.write(temp)
		
def get_class_name():
		import string
		import random
		res = ''.join(random.choices(string.ascii_lowercase, k = 8))
		if frappe.db.get_all("Page Section",filters={"class_name":res}):
			return get_class_name()
		else:
			return res




#added by boopathy from ecommerce business store api on 10/08/2022
def get_product_details(product, isMobile=0, customer=None, current_category=None):
	if 'erp_go1_cms' in frappe.get_installed_apps():
		from erp_go1_cms.erp_go1_cms.api import get_product_details as get_product_details_list
		return get_product_details_list(product, isMobile, customer, current_category)
	if 'go1_cms' in frappe.get_installed_apps():
		from go1_cms.go1_cms.v2.product import get_list_product_details as get_product_details_list
		return get_product_details_list(product)

def get_child_categories(category):
	try:
		if category:
			lft, rgt = frappe.db.get_value('Product Category', category, ['lft', 'rgt'])
			product_category = DocType('Product Category')
			categories = (
			    frappe.qb.from_(product_category)
			    .select(product_category.name)
			    .where(
			        product_category.is_active == 1, 
			        product_category.disable_in_website == 0, 
			        product_category.lft >= lft,  
			        product_category.rgt <= rgt  
			    )
			).run(as_dict=True)
			# if lft != "lft" and rgt != "rgt":
			# return frappe.db.sql('''select name from `tabProduct Category` where is_active = 1 and disable_in_website = 0 and lft >= {lft} and rgt <= {rgt}'''.format(lft=lft, rgt=rgt), as_dict=1)
		# else:
		# 	return frappe.db.sql('''select name from `tabProduct Category` where is_active = 1 and disable_in_website = 0 and parent_product_category = %(parent_categiry)s '''.format(parent_categiry=category), as_dict=1)

		# return frappe.db.get_all('Product Category', fields=['name'], filters={'is_active': 1, 'parent_product_category': category}, limit_page_length=100)
	except Exception:
		frappe.log_error(frappe.get_traceback(), 'go1_cms.go1_cms.api.get_child_categories')